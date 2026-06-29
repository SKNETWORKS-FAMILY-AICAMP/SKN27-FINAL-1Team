"""processed 크롤 MD → review.csv / comment.csv."""

from __future__ import annotations

import pathlib
import re
import sys

import pandas as pd
from tqdm import tqdm

from etl.recipe.preprocessing.recipe_processing import save_recipe_data

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
CRAWL_DIR = ROOT / "storage" / "processed" / "crawling_recipes"
REVIEW_CSV = ROOT / "storage" / "processed" / "recipe" / "review.csv"
COMMENT_CSV = ROOT / "storage" / "processed" / "recipe" / "comment.csv"

CHEF_REPLY = "쉐프의 한마디"
_RE_USER_REACTIONS = re.compile(r"<!--\s*user_reactions\s*-->\s*\n(.*)", re.DOTALL)
_RE_REVIEW_COUNT = re.compile(r"^요리 후기\s+(\d+)", re.MULTILINE)
_RE_COMMENT_COUNT = re.compile(r"^댓글\s+(\d+)", re.MULTILINE)
_RE_HEADER = re.compile(r"^\*\*(?P<author>[^*]*)\*\*\s+(?P<rest>.+)$")
_FOOTER_MARKERS = ("![파일첨부]", "[#", "[전체보기]")
_STOP_REVIEW = ("![](https://recipe1.ezmember.co.kr/img/icon_reply3.gif)",)
_STOP_COMMENT = ("![파일첨부]", "[#", "[전체보기]")
# 이미지 링크 → [ ![](url) ](javascript:viewLargePic('...') 또는 viewLargePic\('...'\))
_RE_JS_VIEW_PIC = r"javascript:viewLargePic\\?\('(?:[^'\\]|\\.)*'\\?\)"
_RE_MD_LINK_IMG = re.compile(
    rf"\[\s*!\[[^\]]*\]\([^)]*\)\s*\]\({_RE_JS_VIEW_PIC}\)"
)
_RE_ORPHAN_JS_PIC = re.compile(rf"\[\s*\]\({_RE_JS_VIEW_PIC}\)")
_RE_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_RE_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_RE_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_RE_HTML_TAG = re.compile(r"<[^>]+>")


def _link_label(m: re.Match[str]) -> str:
    return m.group(1).strip()


def strip_markup(text: str) -> str:
    """마크다운 이미지·링크·볼드·HTML 태그 제거 후 순수 텍스트만 반환."""
    text = _RE_MD_LINK_IMG.sub("", text)
    text = _RE_ORPHAN_JS_PIC.sub("", text)
    text = _RE_MD_IMAGE.sub("", text)
    text = _RE_MD_LINK.sub(_link_label, text)
    text = _RE_MD_BOLD.sub(r"\1", text)
    text = _RE_HTML_TAG.sub("", text)
    text = re.sub(r"\*\*\s*$", "", text, flags=re.MULTILINE)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line and line != ")").strip()


def extract_user_reactions(text: str) -> str | None:
    m = _RE_USER_REACTIONS.search(text)
    if m:
        return m.group(1).strip()
    return None


def _trim_at_footer(block: str) -> str:
    ends = [block.find(marker) for marker in _FOOTER_MARKERS if block.find(marker) != -1]
    return block[: min(ends)].strip() if ends else block.strip()


def split_review_comment_blocks(reactions: str) -> tuple[str | None, str | None]:
    comment_m = _RE_COMMENT_COUNT.search(reactions)
    review_m = _RE_REVIEW_COUNT.search(reactions)

    review_block: str | None = None
    if review_m and int(review_m.group(1)) > 0:
        start = review_m.start()
        end = comment_m.start() if comment_m else len(reactions)
        review_block = _trim_at_footer(reactions[start:end])

    comment_block: str | None = None
    if comment_m and int(comment_m.group(1)) > 0:
        comment_block = _trim_at_footer(reactions[comment_m.start() :])

    return review_block, comment_block


def _parse_h4_blocks(block: str) -> list[tuple[str, str, str]]:
    parts = re.split(r"^####\s+", block, flags=re.MULTILINE)
    results: list[tuple[str, str, str]] = []
    for part in parts[1:]:
        part = part.strip()
        if not part:
            continue
        lines = part.split("\n", 1)
        header_line = lines[0].strip()
        body = lines[1] if len(lines) > 1 else ""
        m = _RE_HEADER.match(header_line)
        if not m:
            continue
        results.append((m.group("author").strip(), m.group("rest"), body))
    return results


def _clean_content(body: str, *, stop_markers: tuple[str, ...]) -> str:
    lines: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if any(marker in stripped for marker in stop_markers):
            break
        if stripped.startswith("####"):
            break
        if not stripped or stripped == "등록" or stripped == "![]()":
            continue
        if stripped.startswith("[!["):
            continue
        if stripped.startswith("!["):
            continue
        lines.append(stripped)
    return strip_markup("\n".join(lines))


def parse_reviews(block: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for author, rest, body in _parse_h4_blocks(block):
        if author == CHEF_REPLY:
            continue
        if "icon_star2_on" not in rest:
            continue
        content = _clean_content(body, stop_markers=_STOP_REVIEW)
        if not content:
            continue
        rows.append(
            {
                "author_name": author,
                "star_count": rest.count("icon_star2_on"),
                "content": content,
            }
        )
    return rows


def parse_comments(block: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for author, rest, body in _parse_h4_blocks(block):
        if "icon_star2_on" in rest:
            continue
        content = _clean_content(body, stop_markers=_STOP_COMMENT)
        if not content:
            continue
        rows.append({"author_name": author, "content": content})
    return rows


def gather_from_md(path: pathlib.Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return [], []

    reactions = extract_user_reactions(text)
    if not reactions:
        return [], []

    recipe_id = int(path.stem)
    review_block, comment_block = split_review_comment_blocks(reactions)

    reviews: list[dict[str, object]] = []
    if review_block:
        for row in parse_reviews(review_block):
            reviews.append({"recipe_id": recipe_id, **row})

    comments: list[dict[str, object]] = []
    if comment_block:
        for row in parse_comments(comment_block):
            comments.append({"recipe_id": recipe_id, **row})

    return reviews, comments


def _assign_ids(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df.insert(0, "id", range(1, len(df) + 1))
    return df


def _self_check() -> None:
    sample_img = (
        "맛있어요\n"
        "[ ![](https://example.com/a.jpg) ](javascript:viewLargePic('https://example.com/b.jpg'))"
    )
    plain = strip_markup(sample_img)
    assert plain == "맛있어요"
    sample_js_pic = (
        "오늘 아침 식사로 잘 먹었어요\n"
        "[ ![](https://example.com/a.jpg) ](javascript:viewLargePic\\('https://example.com/b.jpg\\'))"
    )
    assert strip_markup(sample_js_pic) == "오늘 아침 식사로 잘 먹었어요"
    assert strip_markup("**여언** [mail@test.com](mailto:mail@test.com)입니다") == "여언 mail@test.com입니다"
    assert strip_markup("후기\n[ ](/profile/review.html?uid=123)") == "후기"
    assert strip_markup("감사~**") == "감사~"
    assert strip_markup("nas**** 버섯") == "nas**** 버섯"

    samples = {
        7016902: CRAWL_DIR / "7016902.md",
        7016815: CRAWL_DIR / "7016815.md",
        7017096: CRAWL_DIR / "7017096.md",
    }
    for recipe_id, path in samples.items():
        assert path.exists(), f"missing sample {path}"

    reviews_6902, comments_6902 = gather_from_md(samples[7016902])
    assert len(reviews_6902) == 1
    assert reviews_6902[0]["author_name"] == "kim"
    assert reviews_6902[0]["star_count"] == 5
    assert reviews_6902[0]["recipe_id"] == 7016902
    assert "깻잎나물" in str(reviews_6902[0]["content"])
    assert "![" not in str(reviews_6902[0]["content"])
    assert not comments_6902

    _, comments_6815 = gather_from_md(samples[7016815])
    assert len(comments_6815) == 1
    assert comments_6815[0]["author_name"] == "성원"
    assert comments_6815[0]["recipe_id"] == 7016815

    _, comments_7096 = gather_from_md(samples[7017096])
    assert len(comments_7096) == 4
    assert comments_7096[0]["author_name"] == "여언"
    authors = {row["author_name"] for row in comments_7096}
    assert "슈퍼파워" in authors
    assert "알리체" in authors

    # 후기 이미지 첨부 샘플
    reviews_6926, _ = gather_from_md(CRAWL_DIR / "7016926.md")
    assert reviews_6926
    assert "![" not in str(reviews_6926[0]["content"])
    assert "javascript:" not in str(reviews_6926[0]["content"])
    assert not str(reviews_6926[0]["content"]).rstrip().endswith(")")


def main() -> None:
    paths = sorted(CRAWL_DIR.glob("*.md"))
    all_reviews: list[dict[str, object]] = []
    all_comments: list[dict[str, object]] = []
    fail = 0

    for path in tqdm(paths, desc="gather reviews/comments"):
        try:
            reviews, comments = gather_from_md(path)
            all_reviews.extend(reviews)
            all_comments.extend(comments)
        except Exception as exc:
            print(f"fail {path.name}: {exc}", file=sys.stderr)
            fail += 1

    review_df = _assign_ids(all_reviews)
    comment_df = _assign_ids(all_comments)

    if review_df.empty:
        review_df = pd.DataFrame(columns=["id", "recipe_id", "star_count", "author_name", "content"])
    else:
        review_df = review_df[["id", "recipe_id", "star_count", "author_name", "content"]]

    if comment_df.empty:
        comment_df = pd.DataFrame(columns=["id", "recipe_id", "author_name", "content"])
    else:
        comment_df = comment_df[["id", "recipe_id", "author_name", "content"]]

    save_recipe_data(review_df, REVIEW_CSV)
    save_recipe_data(comment_df, COMMENT_CSV)
    print(f"gather done: reviews={len(review_df)} comments={len(comment_df)} fail={fail}")


if __name__ == "__main__":
    _self_check()
    main()
