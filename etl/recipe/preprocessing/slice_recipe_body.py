"""크롤 원본 MD → 본문·작성자·사용자 반응만 남긴 processed MD."""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
RAW_DIR = ROOT / "storage" / "raw" / "crawling_recipes"
OUT_DIR = ROOT / "storage" / "processed" / "crawling_recipes"

BODY_START = ("![main thumb]",)
BODY_END = ("관련 상품",)
AUTHOR_START = ("**레시피 작성자**",)
AUTHOR_END = ("![닫기]",)
REACTIONS_START = ("요리 후기", "댓글")
REACTIONS_END = ("맛보장 레시피",)

_RE_REVIEW = re.compile(r"^요리 후기\s+\d+", re.MULTILINE)
_RE_COMMENT = re.compile(r"^댓글\s+\d+", re.MULTILINE)


def _find_earliest(text: str, markers: tuple[str, ...], *, after: int = 0) -> int | None:
    positions = [text.find(m, after) for m in markers]
    valid = [p for p in positions if p != -1]
    return min(valid) if valid else None


def _exclude_marker_line(text: str, start: int, end: int) -> str:
    """마커가 있는 줄 전체를 제외하고 슬라이스 (예: **제목****관련 상품**)."""
    line_start = text.rfind("\n", start, end)
    cut = line_start if line_start != -1 else end
    return text[start:cut].strip()


def _find_body_start(text: str) -> int | None:
    pos = _find_earliest(text, BODY_START)
    if pos is not None:
        return pos
    for line in text.splitlines(keepends=True):
        if line.startswith("### ") and not line.startswith("### 동영상"):
            return text.find(line)
    return None


def slice_recipe_body(raw: str) -> str | None:
    start = _find_body_start(raw)
    if start is None:
        return None
    end = _find_earliest(raw, BODY_END, after=start + 1)
    if end is None:
        return None
    body = _exclude_marker_line(raw, start, end)
    return body or None


def slice_recipe_author(raw: str) -> str | None:
    start = _find_earliest(raw, AUTHOR_START)
    if start is None:
        return None
    end = _find_earliest(raw, AUTHOR_END, after=start + 1)
    if end is None:
        return None
    author = raw[start:end].strip()
    return author or None


def _find_reactions_start(raw: str) -> int | None:
    body_end = _find_earliest(raw, BODY_END)
    after = body_end if body_end is not None else 0
    positions: list[int] = []
    for pattern in (_RE_REVIEW, _RE_COMMENT):
        m = pattern.search(raw, after)
        if m:
            positions.append(m.start())
    return min(positions) if positions else None


def slice_user_reactions(raw: str) -> str | None:
    start = _find_reactions_start(raw)
    if start is None:
        return None
    end = _find_earliest(raw, REACTIONS_END, after=start + 1)
    if end is None:
        return None
    reactions = _exclude_marker_line(raw, start, end)
    return reactions or None


def slice_crawled_recipe(raw: str) -> str | None:
    body = slice_recipe_body(raw)
    if body is None:
        return None
    parts: list[str] = [f"<!-- recipe_body -->\n{body}"]
    if author := slice_recipe_author(raw):
        parts.append(f"<!-- recipe_author -->\n{author}")
    if reactions := slice_user_reactions(raw):
        parts.append(f"<!-- user_reactions -->\n{reactions}")
    return "\n\n".join(parts)


def _self_check() -> None:
    sample = """\
junk header
![main thumb](https://example.com/thumb.png)
### 테스트 레시피
2인분
**재료**
- 물
![팁-주의사항](https://example.com/tip.gif)
    팁 내용
**테스트레시피****관련 상품**
* coupang ad
**등록일 : 2024-01-01**
**레시피 작성자** About the writer
[작성자](/profile/index.html?uid=testuid)
![닫기](https://example.com/close.gif)
#### 계량법 안내
modal junk
요리 후기 1
####  **리뷰어** 2024-01-02  ![](star)
맛있어요
댓글 1
####  **댓글러** 2024-01-03|[답글](javascript:void(0);)
좋네요
[#태그](/recipe/list.html?q=tag)
**다른레시피** **맛보장 레시피**
footer junk
"""
    out = slice_crawled_recipe(sample)
    assert out is not None
    assert "<!-- recipe_body -->" in out
    assert "![main thumb]" in out
    assert "### 테스트 레시피" in out
    assert "관련 상품" not in out
    assert "맛보장 레시피" not in out
    assert "<!-- recipe_author -->" in out
    assert "**레시피 작성자**" in out
    assert "계량법 안내" not in out
    assert "<!-- user_reactions -->" in out
    assert "요리 후기 1" in out
    assert "댓글 1" in out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = skip = fail = 0
    for path in sorted(RAW_DIR.glob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"fail read {path.name}: {e}", file=sys.stderr)
            fail += 1
            continue
        sliced = slice_crawled_recipe(raw)
        if sliced is None:
            print(f"skip {path.name}: recipe body markers not found", file=sys.stderr)
            skip += 1
            continue
        out_path = OUT_DIR / path.name
        try:
            out_path.write_text(sliced, encoding="utf-8")
        except OSError as e:
            print(f"fail write {path.name}: {e}", file=sys.stderr)
            fail += 1
            continue
        ok += 1
    print(f"slice done: ok={ok} skip={skip} fail={fail}")


if __name__ == "__main__":
    _self_check()
    main()
