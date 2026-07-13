"""10000recipe 페이지의 현재 조회수를 수집해 recipe_fix.csv에 반영한다.

기본 실행은 dry-run이다. 실제 반영은 ``--apply``를 명시해야 하며, 반영 전
원본 CSV를 타임스탬프 백업하고 임시 파일을 이용해 원자적으로 교체한다.
기존 ``INQ_CNT``와 관련 파생 컬럼은 수정하지 않고, 2026년 현재값과 변화량을
새 컬럼으로만 기록한다. 따라서 기존 ML baseline은 그대로 재현할 수 있다.
"""

from __future__ import annotations

import argparse
import pathlib
import random
import shutil
import sys
import time
from datetime import datetime, timezone
from math import log1p
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

ROOT = pathlib.Path(__file__).resolve().parents[3]
if __package__ is None:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry

RECIPE_FIX_CSV = ROOT / "storage" / "processed" / "recipe" / "recipe_fix.csv"
CHECKPOINT_CSV = (
    ROOT / "storage" / "processed" / "recipe" / "recipe_view_crawl_checkpoint.csv"
)
RECIPE_URL_TEMPLATE = "https://www.10000recipe.com/recipe/{recipe_id}"
ROBOTS_URL = "https://www.10000recipe.com/robots.txt"
BASE_VIEW_COL = "INQ_CNT_2024"
CURRENT_VIEW_COL = "INQ_CNT_2026"
BASE_VIEW_RATE_COL = "INQ_CNT_RATE_2024"
BASE_VIEW_LOG_COL = "INQ_CNT_LOG_2024"
BASE_VIEW_LOG_CENTERED_COL = "INQ_CNT_LOG_CENTERED_2024"
CURRENT_VIEW_RATE_COL = "INQ_CNT_RATE_2026"
CURRENT_VIEW_LOG_COL = "INQ_CNT_LOG_2026"
CURRENT_VIEW_LOG_CENTERED_COL = "INQ_CNT_LOG_CENTERED_2026"
VIEW_DELTA_COL = "INQ_CNT_DELTA_2024_2026"
VIEW_GROWTH_COL = "INQ_CNT_GROWTH_RATE_2024_2026"
VIEW_CRAWLED_AT_COL = "INQ_CNT_2026_CRAWLED_AT_UTC"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Referer": "https://www.10000recipe.com/",
}


def build_session(user_agent: str = DEFAULT_USER_AGENT) -> requests.Session:
    """재시도와 브라우저 호환 헤더가 설정된 세션을 만든다."""
    session = requests.Session()
    session.headers.update({**DEFAULT_HEADERS, "User-Agent": user_agent})
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=1, pool_maxsize=1)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def assert_robots_allowed(
    session: requests.Session,
    *,
    user_agent: str,
    target_url: str,
    ignore_robots: bool = False,
) -> None:
    """robots.txt가 대상 URL 수집을 허용하는지 검사한다."""
    if ignore_robots:
        return
    try:
        response = session.get(ROBOTS_URL, timeout=(5, 15))
        if response.status_code == 404:
            return
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            "robots.txt를 확인하지 못했습니다. 네트워크를 확인하거나, 정책을 직접 "
            "확인한 경우에만 --ignore-robots를 사용하세요."
        ) from exc

    parser = RobotFileParser()
    parser.set_url(ROBOTS_URL)
    parser.parse(response.text.splitlines())
    if not parser.can_fetch(user_agent, target_url):
        raise RuntimeError(f"robots.txt가 수집을 허용하지 않습니다: {target_url}")


def extract_view_count(html: str) -> int:
    """레시피 HTML의 조회수 카운터를 정수로 반환한다."""
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one(".view_cate_num .hit")
    if node is None:
        raise ValueError("조회수 요소(.view_cate_num .hit)를 찾지 못했습니다")
    text = node.get_text(strip=True).replace(",", "")
    if not text.isdigit():
        raise ValueError(f"조회수 값이 정수가 아닙니다: {node.get_text(strip=True)!r}")
    return int(text)


def fetch_view_count(
    session: requests.Session,
    recipe_id: int,
    *,
    timeout: tuple[float, float],
) -> tuple[int, str]:
    url = RECIPE_URL_TEMPLATE.format(recipe_id=recipe_id)
    response = session.get(url, timeout=timeout)
    if response.status_code == 404:
        raise ValueError("레시피 페이지가 존재하지 않습니다(404)")
    response.raise_for_status()
    return extract_view_count(response.text), url


def load_checkpoint(path: pathlib.Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    checkpoint = pd.read_csv(path)
    if "RCP_SNO" not in checkpoint.columns or "status" not in checkpoint.columns:
        raise ValueError(f"잘못된 체크포인트 파일입니다: {path}")
    checkpoint["RCP_SNO"] = pd.to_numeric(
        checkpoint["RCP_SNO"], errors="coerce"
    ).astype("Int64")
    return checkpoint


def save_checkpoint(rows: list[dict[str, object]], path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    pd.DataFrame(rows).to_csv(tmp, index=False, encoding="utf-8-sig")
    tmp.replace(path)


def crawl_view_counts(
    recipe_df: pd.DataFrame,
    *,
    session: requests.Session,
    checkpoint_path: pathlib.Path,
    min_delay: float,
    jitter: float,
    timeout: tuple[float, float],
    checkpoint_every: int,
    limit: int | None = None,
    fresh: bool = False,
) -> pd.DataFrame:
    """조회수를 순차 수집하며 성공·실패 결과를 체크포인트에 저장한다."""
    if "RCP_SNO" not in recipe_df.columns or "INQ_CNT" not in recipe_df.columns:
        raise ValueError("입력 CSV에 RCP_SNO와 INQ_CNT 컬럼이 필요합니다")
    if min_delay < 0 or jitter < 0:
        raise ValueError("delay와 jitter는 0 이상이어야 합니다")
    if checkpoint_every < 1:
        raise ValueError("checkpoint_every는 1 이상이어야 합니다")

    previous = pd.DataFrame() if fresh else load_checkpoint(checkpoint_path)
    rows = previous.to_dict("records") if not previous.empty else []
    completed = {
        int(row["RCP_SNO"])
        for row in rows
        if row.get("status") == "ok" and pd.notna(row.get("RCP_SNO"))
    }
    targets = recipe_df.loc[~recipe_df["RCP_SNO"].isin(completed)].copy()
    if limit is not None:
        targets = targets.head(limit)

    attempted = 0
    for row in tqdm(
        targets.itertuples(index=False), total=len(targets), desc="조회수 수집"
    ):
        recipe_id = int(row.RCP_SNO)
        old_count = int(row.INQ_CNT)
        started = time.monotonic()
        result: dict[str, object] = {
            "RCP_SNO": recipe_id,
            "old_INQ_CNT": old_count,
            "current_INQ_CNT": pd.NA,
            "status": "error",
            "error": "",
            "url": RECIPE_URL_TEMPLATE.format(recipe_id=recipe_id),
            "crawled_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        try:
            current, url = fetch_view_count(session, recipe_id, timeout=timeout)
            result.update(current_INQ_CNT=current, status="ok", url=url)
        except (requests.RequestException, ValueError) as exc:
            result["error"] = str(exc)[:500]
        rows.append(result)
        attempted += 1

        if attempted % checkpoint_every == 0:
            save_checkpoint(rows, checkpoint_path)

        elapsed = time.monotonic() - started
        requested_delay = min_delay + random.uniform(0.0, jitter)
        time.sleep(max(0.0, requested_delay - elapsed))

    save_checkpoint(rows, checkpoint_path)
    return pd.DataFrame(rows)


def apply_view_counts(
    recipe_df: pd.DataFrame,
    crawl_df: pd.DataFrame,
    *,
    allow_decrease: bool = False,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """기존 조회수 컬럼은 유지하고 2024·2026 조회수와 변화량만 추가한다.

    ``INQ_CNT_GROWTH_RATE_2024_2026``는 ``(2026 - 2024) / 2024``이다.
    2024년 조회수가 0이면 분모를 정의할 수 없으므로 결측값으로 둔다.
    """
    successful = crawl_df.loc[crawl_df["status"].eq("ok")].copy()
    successful["current_INQ_CNT"] = pd.to_numeric(
        successful["current_INQ_CNT"], errors="coerce"
    )
    successful = successful.dropna(subset=["RCP_SNO", "current_INQ_CNT"])
    successful = successful.drop_duplicates("RCP_SNO", keep="last")
    current_by_id = successful.set_index("RCP_SNO")["current_INQ_CNT"]
    crawled_at_by_id = successful.set_index("RCP_SNO").get("crawled_at_utc")

    out = recipe_df.copy()
    # out을 갱신한 뒤에도 변경 전 값과 정확히 비교할 수 있도록 독립 복사한다.
    old = pd.to_numeric(out["INQ_CNT"], errors="coerce").copy()
    candidate = out["RCP_SNO"].map(current_by_id)
    available = candidate.notna()
    decreasing = available & old.notna() & candidate.lt(old)
    accepted = available if allow_decrease else available & ~decreasing

    # 최초 반영 시 기존 조회수와 파생값을 2024년 스냅샷으로 고정한다.
    # 재실행할 때는 이미 저장된 기준값을 덮어쓰지 않는다.
    if BASE_VIEW_COL not in out.columns:
        out[BASE_VIEW_COL] = old
    else:
        out[BASE_VIEW_COL] = pd.to_numeric(out[BASE_VIEW_COL], errors="coerce")
    base_counts = pd.to_numeric(out[BASE_VIEW_COL], errors="coerce")
    if BASE_VIEW_RATE_COL not in out.columns:
        if "INQ_CNT_RATE" in out.columns:
            out[BASE_VIEW_RATE_COL] = pd.to_numeric(
                out["INQ_CNT_RATE"], errors="coerce"
            )
        else:
            out[BASE_VIEW_RATE_COL] = base_counts / base_counts.max()
    if BASE_VIEW_LOG_COL not in out.columns:
        if "INQ_CNT_LOG" in out.columns:
            out[BASE_VIEW_LOG_COL] = pd.to_numeric(
                out["INQ_CNT_LOG"], errors="coerce"
            )
        else:
            out[BASE_VIEW_LOG_COL] = base_counts.map(log1p)
    if BASE_VIEW_LOG_CENTERED_COL not in out.columns:
        if "INQ_CNT_LOG_CENTERED" in out.columns:
            out[BASE_VIEW_LOG_CENTERED_COL] = pd.to_numeric(
                out["INQ_CNT_LOG_CENTERED"], errors="coerce"
            )
        else:
            out[BASE_VIEW_LOG_CENTERED_COL] = (
                out[BASE_VIEW_LOG_COL] - out[BASE_VIEW_LOG_COL].mean()
            )
    if CURRENT_VIEW_COL not in out.columns:
        out[CURRENT_VIEW_COL] = pd.NA
    out.loc[accepted, CURRENT_VIEW_COL] = candidate.loc[accepted].astype("int64")

    if VIEW_CRAWLED_AT_COL not in out.columns:
        out[VIEW_CRAWLED_AT_COL] = pd.NA
    if crawled_at_by_id is not None:
        crawled_at = out["RCP_SNO"].map(crawled_at_by_id)
        out.loc[accepted, VIEW_CRAWLED_AT_COL] = crawled_at.loc[accepted]

    current_counts = pd.to_numeric(out[CURRENT_VIEW_COL], errors="coerce")
    out[VIEW_DELTA_COL] = current_counts - base_counts
    out[VIEW_GROWTH_COL] = pd.NA
    valid_growth = base_counts.gt(0) & current_counts.notna()
    out.loc[valid_growth, VIEW_GROWTH_COL] = (
        out.loc[valid_growth, VIEW_DELTA_COL] / base_counts.loc[valid_growth]
    )

    # 연도 명시 최신 파생값은 실제 2026 수집값이 있는 행에만 계산한다.
    # 기존 무연도 파생 컬럼은 2024 baseline 보존을 위해 수정하지 않는다.
    valid_current = current_counts.notna() & current_counts.ge(0)
    out[CURRENT_VIEW_RATE_COL] = pd.NA
    if valid_current.any():
        out.loc[valid_current, CURRENT_VIEW_RATE_COL] = (
            current_counts.loc[valid_current] / current_counts.loc[valid_current].max()
        )
    out[CURRENT_VIEW_LOG_COL] = pd.NA
    out.loc[valid_current, CURRENT_VIEW_LOG_COL] = current_counts.loc[
        valid_current
    ].map(log1p)
    out[CURRENT_VIEW_LOG_CENTERED_COL] = pd.NA
    if valid_current.any():
        current_log_mean = out.loc[valid_current, CURRENT_VIEW_LOG_COL].mean()
        out.loc[valid_current, CURRENT_VIEW_LOG_CENTERED_COL] = (
            out.loc[valid_current, CURRENT_VIEW_LOG_COL] - current_log_mean
        )

    changed = accepted & candidate.ne(old)
    summary = {
        "successful": int(available.sum()),
        "different_from_2024": int(changed.sum()),
        "same_as_2024": int((accepted & candidate.eq(old)).sum()),
        "rejected_decrease": int(decreasing.sum()) if not allow_decrease else 0,
    }
    return out, summary


def atomic_write_with_backup(df: pd.DataFrame, path: pathlib.Path) -> pathlib.Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.stem}.backup_{timestamp}{path.suffix}")
    shutil.copy2(path, backup)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        df.to_csv(tmp, index=False, encoding="utf-8-sig")
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return backup


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=pathlib.Path, default=RECIPE_FIX_CSV)
    parser.add_argument("--checkpoint", type=pathlib.Path, default=CHECKPOINT_CSV)
    parser.add_argument("--apply", action="store_true", help="recipe_fix.csv에 실제 반영")
    parser.add_argument("--fresh", action="store_true", help="기존 체크포인트를 무시하고 재수집")
    parser.add_argument("--limit", type=int, help="앞의 N개만 수집(샘플 실행용)")
    parser.add_argument("--min-delay", type=float, default=1.5, help="요청 간 최소 간격(초)")
    parser.add_argument("--jitter", type=float, default=1.0, help="요청 간 무작위 추가 간격(초)")
    parser.add_argument("--connect-timeout", type=float, default=5.0)
    parser.add_argument("--read-timeout", type=float, default=20.0)
    parser.add_argument("--checkpoint-every", type=int, default=20)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--ignore-robots", action="store_true")
    parser.add_argument("--allow-decrease", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    recipe_df = pd.read_csv(args.input)
    if recipe_df["RCP_SNO"].duplicated().any():
        raise ValueError("입력 CSV에 중복 RCP_SNO가 있습니다")

    session = build_session(args.user_agent)
    first_id = int(recipe_df.iloc[0]["RCP_SNO"])
    assert_robots_allowed(
        session,
        user_agent=args.user_agent,
        target_url=RECIPE_URL_TEMPLATE.format(recipe_id=first_id),
        ignore_robots=args.ignore_robots,
    )
    crawl_df = crawl_view_counts(
        recipe_df,
        session=session,
        checkpoint_path=args.checkpoint,
        min_delay=args.min_delay,
        jitter=args.jitter,
        timeout=(args.connect_timeout, args.read_timeout),
        checkpoint_every=args.checkpoint_every,
        limit=args.limit,
        fresh=args.fresh,
    )
    updated_df, summary = apply_view_counts(
        recipe_df, crawl_df, allow_decrease=args.allow_decrease
    )
    failures = int(crawl_df["status"].ne("ok").sum())
    print(f"수집 결과: {summary}, failures={failures}")
    print(f"체크포인트: {args.checkpoint}")

    if not args.apply:
        print("dry-run 완료: CSV는 변경하지 않았습니다. 실제 반영은 --apply를 사용하세요.")
        return

    backup = atomic_write_with_backup(updated_df, args.input)
    print(f"반영 완료: {args.input}")
    print(f"백업 파일: {backup}")


if __name__ == "__main__":
    main()
