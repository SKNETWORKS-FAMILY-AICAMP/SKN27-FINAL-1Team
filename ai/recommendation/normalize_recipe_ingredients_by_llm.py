"""recipe_fix.csv 재료 정규화 + nodes_alias 매칭 → recipe_ingredient_alias.csv."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
if __package__ is None:
    sys.path.insert(0, str(ROOT))

from etl.recipe.load_to_postgres.loader import (
    clean_ingredient_name,
    normalize_ingredient_name,
    parse_ingredient_rows,
)

if __package__ is None:
    from ai.recommendation.openai_model import OpenAIClient
else:
    from .openai_model import OpenAIClient

logger = logging.getLogger(__name__)

MODEL_NAME = "gpt-5.5"
CANDIDATE_LIMIT = 100

RECIPE_FIX_CSV = ROOT / "storage" / "processed" / "recipe" / "recipe_fix.csv"
ALIAS_CSV = ROOT / "storage" / "processed" / "food_guide" / "nodes_alias.csv"
OUTPUT_CSV = ROOT / "storage" / "processed" / "recipe" / "recipe_ingredient_alias.csv"
PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "recipe_ingredient_normalize.md"

OUTPUT_COLUMNS = (
    "RCP_SNO",
    "CKG_NM",
    "ingredients_raw",
    "aliases_matched",
    "ingredients_normalized",
    "others_count",
    "others_items",
)


def _match_key(value: str | None) -> str:
    """IngredientNameMatcher와 동일한 정규화 키."""
    if not value:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]|\uff08[^\uff09]*\uff09|<[^>]*>", "", text)
    text = re.sub(
        r"\d+(?:\.\d+)?\s*(?:kg|g|ml|l|\uac1c\uc785|\uac1c|\uc785|\ubd09|\ud329|\ubcd1|\uce94)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"[^0-9a-z\uac00-\ud7a3]+", "", text)
    return text


@dataclass(frozen=True)
class AliasEntry:
    alias_id: str
    name: str
    key: str


class AliasIndex:
    """nodes_alias.csv 기반 조회·후보 축소."""

    def __init__(self, entries: list[AliasEntry]) -> None:
        self._entries = entries
        self._by_id = {entry.alias_id: entry for entry in entries}
        self._by_key: dict[str, AliasEntry] = {}
        for entry in entries:
            self._by_key.setdefault(entry.key, entry)

    @classmethod
    def from_csv(cls, path: Path | str = ALIAS_CSV) -> AliasIndex:
        df = pd.read_csv(path)
        entries: list[AliasEntry] = []
        for _, row in df.iterrows():
            alias_id = str(row["alias_id"]).strip()
            name = str(row["name"]).strip()
            key = _match_key(name)
            if alias_id and name and key:
                entries.append(AliasEntry(alias_id=alias_id, name=name, key=key))
        return cls(entries)

    def get(self, alias_id: str | None) -> AliasEntry | None:
        if not alias_id:
            return None
        return self._by_id.get(str(alias_id).strip())

    def rule_match(self, name: str) -> AliasEntry | None:
        key = _match_key(name)
        if not key:
            return None
        exact = self._by_key.get(key)
        if exact:
            return exact
        best: AliasEntry | None = None
        best_len = 0
        for entry in self._entries:
            if len(entry.key) < 2:
                continue
            if entry.key in key or key in entry.key:
                if len(entry.key) > best_len:
                    best = entry
                    best_len = len(entry.key)
        return best

    def candidates_for_ingredients(
        self,
        ingredient_names: list[str],
        *,
        limit: int = CANDIDATE_LIMIT,
    ) -> list[dict[str, str]]:
        """재료별 규칙 후보를 모아 상한까지 반환."""
        seen: set[str] = set()
        result: list[dict[str, str]] = []

        def add(entry: AliasEntry) -> None:
            if entry.alias_id in seen:
                return
            seen.add(entry.alias_id)
            result.append({"alias_id": entry.alias_id, "name": entry.name})

        for name in ingredient_names:
            cleaned = clean_ingredient_name(name) or name.strip()
            for probe in (name, cleaned):
                matched = self.rule_match(probe)
                if matched:
                    add(matched)
            key = _match_key(cleaned)
            if key:
                for entry in sorted(self._entries, key=lambda item: len(item.key), reverse=True):
                    if len(entry.key) < 2:
                        continue
                    if entry.key in key or key in entry.key:
                        add(entry)
                        if len(result) >= limit:
                            return result[:limit]
            if len(result) >= limit:
                break

        return result[:limit]


def _load_prompt_templates() -> tuple[str, str]:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    system_part, user_part = text.split("# User", maxsplit=1)
    system = system_part.removeprefix("# System").strip()
    user = user_part.strip()
    return system, user


def _build_user_prompt(
    template: str,
    *,
    recipe_name: str,
    ingredients: list[list[str]],
    alias_candidates: list[dict[str, str]],
) -> str:
    return (
        template.replace("{{recipe_name}}", recipe_name)
        .replace("{{ingredients_json}}", json.dumps(ingredients, ensure_ascii=False))
        .replace("{{alias_candidates_json}}", json.dumps(alias_candidates, ensure_ascii=False))
    )


def _strip_triple(item: list[str]) -> list[str]:
    name = str(item[0]).strip() if len(item) > 0 else ""
    amount = str(item[1]).strip() if len(item) > 1 else ""
    unit = str(item[2]).strip() if len(item) > 2 else ""
    return [name, amount, unit]


def assemble_result(
    ingredients_raw: list[list[str]],
    llm_ingredients: list[dict[str, Any]],
    alias_index: AliasIndex,
    valid_alias_ids: set[str],
) -> dict[str, Any]:
    """LLM 응답을 출력 행 dict로 조립."""
    raw_lookup = {str(item[0]).strip(): _strip_triple(item) for item in ingredients_raw if item}

    normalized: list[list[str]] = []
    aliases_matched: list[dict[str, str]] = []
    others_items: list[dict[str, str]] = []
    seen_alias: set[str] = set()

    for item in llm_ingredients:
        raw = str(item.get("raw", "")).strip()
        name = str(item.get("name", "")).strip()
        amount = str(item.get("amount", "")).strip()
        unit = str(item.get("unit", "")).strip()
        alias_id = item.get("alias_id")

        if not raw and raw_lookup:
            # ponytail: raw 누락 시 순서대로 소비하지 않고 스킵 방지용 fallback 없음
            continue
        if not name:
            fallback = raw_lookup.get(raw)
            if fallback:
                name = clean_ingredient_name(fallback[0]) or fallback[0]
                amount = amount or fallback[1]
                unit = unit or fallback[2]

        normalized.append([name, amount, unit])

        alias_id_str = None if alias_id in (None, "", "null") else str(alias_id).strip()
        if alias_id_str and alias_id_str in valid_alias_ids:
            entry = alias_index.get(alias_id_str)
            if entry and entry.alias_id not in seen_alias:
                seen_alias.add(entry.alias_id)
                aliases_matched.append({"alias_id": entry.alias_id, "name": entry.name})
        else:
            others_items.append({"raw": raw, "name": name, "amount": amount, "unit": unit})

    return {
        "ingredients_normalized": normalized,
        "aliases_matched": aliases_matched,
        "others_count": len(others_items),
        "others_items": others_items,
    }


def parse_llm_response(content: str) -> list[dict[str, Any]]:
    data = json.loads(content)
    ingredients = data.get("ingredients")
    if not isinstance(ingredients, list):
        raise ValueError("ingredients 필드가 list가 아님")
    return ingredients


def process_one_recipe(
    *,
    recipe_id: int,
    recipe_name: str,
    ingredients_raw: list[list[str]],
    alias_index: AliasIndex,
    system_prompt: str,
    user_template: str,
    valid_alias_ids: set[str],
) -> dict[str, Any] | None:
    if not ingredients_raw:
        return {
            "RCP_SNO": recipe_id,
            "CKG_NM": recipe_name,
            "ingredients_raw": json.dumps([], ensure_ascii=False),
            "aliases_matched": json.dumps([], ensure_ascii=False),
            "ingredients_normalized": json.dumps([], ensure_ascii=False),
            "others_count": 0,
            "others_items": json.dumps([], ensure_ascii=False),
        }

    probe_names = [str(item[0]) for item in ingredients_raw if item]
    alias_candidates = alias_index.candidates_for_ingredients(probe_names)
    user_prompt = _build_user_prompt(
        user_template,
        recipe_name=recipe_name,
        ingredients=[_strip_triple(item) for item in ingredients_raw],
        alias_candidates=alias_candidates,
    )

    content = OpenAIClient().chat_json(model=MODEL_NAME, system=system_prompt, user=user_prompt)
    if not content:
        return None

    try:
        llm_ingredients = parse_llm_response(content)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("LLM 파싱 실패 recipe=%s: %s — %s", recipe_id, exc, content[:200])
        return None

    assembled = assemble_result(ingredients_raw, llm_ingredients, alias_index, valid_alias_ids)
    return {
        "RCP_SNO": recipe_id,
        "CKG_NM": recipe_name,
        "ingredients_raw": json.dumps(
            [_strip_triple(item) for item in ingredients_raw],
            ensure_ascii=False,
        ),
        "aliases_matched": json.dumps(assembled["aliases_matched"], ensure_ascii=False),
        "ingredients_normalized": json.dumps(assembled["ingredients_normalized"], ensure_ascii=False),
        "others_count": assembled["others_count"],
        "others_items": json.dumps(assembled["others_items"], ensure_ascii=False),
    }


def load_processed_ids(path: Path) -> set[int]:
    if not path.exists():
        return set()
    df = pd.read_csv(path, usecols=["RCP_SNO"])
    return {int(value) for value in df["RCP_SNO"].dropna().unique()}


def ensure_output_header(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        pd.DataFrame(columns=list(OUTPUT_COLUMNS)).to_csv(path, index=False, encoding="utf-8-sig")


def append_result_row(path: Path, row: dict[str, Any]) -> None:
    pd.DataFrame([row], columns=list(OUTPUT_COLUMNS)).to_csv(
        path,
        mode="a",
        header=False,
        index=False,
        encoding="utf-8-sig",
    )


def normalize_recipe_ingredients_by_llm(
    *,
    input_path: Path | str = RECIPE_FIX_CSV,
    output_path: Path | str = OUTPUT_CSV,
    alias_path: Path | str = ALIAS_CSV,
    limit: int | None = None,
    force: bool = False,
) -> int:
    input_path = Path(input_path)
    output_path = Path(output_path)

    if force and output_path.exists():
        output_path.unlink()

    alias_index = AliasIndex.from_csv(alias_path)
    valid_alias_ids = {entry.alias_id for entry in alias_index._entries}
    system_prompt, user_template = _load_prompt_templates()

    OpenAIClient()

    df = pd.read_csv(input_path)
    if "RCP_SNO" not in df.columns or "CKG_MTRL_CN" not in df.columns:
        raise ValueError("필수 컬럼 누락: RCP_SNO, CKG_MTRL_CN")

    processed_ids = set() if force else load_processed_ids(output_path)
    ensure_output_header(output_path)

    pending = df[~df["RCP_SNO"].astype(int).isin(processed_ids)]
    if limit is not None:
        pending = pending.head(limit)

    if pending.empty:
        logger.info("처리 대상 없음 (이미 완료): %s", output_path)
        return 0

    logger.info("처리 대상 %s건 → %s", len(pending), output_path)
    processed = 0

    for _, row in tqdm(pending.iterrows(), total=len(pending), desc="recipe_ingredient_alias"):
        recipe_id = int(row["RCP_SNO"])
        recipe_name = "" if pd.isna(row.get("CKG_NM")) else str(row["CKG_NM"]).strip()
        ingredients_raw = parse_ingredient_rows(row["CKG_MTRL_CN"])

        result = process_one_recipe(
            recipe_id=recipe_id,
            recipe_name=recipe_name,
            ingredients_raw=ingredients_raw,
            alias_index=alias_index,
            system_prompt=system_prompt,
            user_template=user_template,
            valid_alias_ids=valid_alias_ids,
        )
        if result is None:
            logger.warning("행 스킵 (LLM 실패): RCP_SNO=%s", recipe_id)
            continue

        append_result_row(output_path, result)
        processed += 1

    logger.info("저장 완료 (%s건): %s", processed, output_path)
    return processed


def _self_check() -> None:
    sample_raw = parse_ingredient_rows("[['양파', '1', '개'], ['간장', '2', 't']]")
    assert sample_raw == [["양파", "1", "개"], ["간장", "2", "t"]]

    index = AliasIndex(
        [
            AliasEntry("alias_1", "간장", _match_key("간장")),
            AliasEntry("alias_2", "양파", _match_key("양파")),
            AliasEntry("alias_3", "다진마늘", _match_key("다진마늘")),
        ]
    )
    assert index.rule_match("국간장").alias_id == "alias_1"
    assert index.rule_match("양파").alias_id == "alias_2"

    candidates = index.candidates_for_ingredients(["다진 마늘", "양파"])
    candidate_ids = {item["alias_id"] for item in candidates}
    assert "alias_2" in candidate_ids

    mock_llm = json.dumps(
        {
            "ingredients": [
                {"raw": "양파", "name": "양파", "amount": "1", "unit": "개", "alias_id": "alias_2"},
                {"raw": "간장", "name": "간장", "amount": "2", "unit": "큰술", "alias_id": "alias_1"},
                {"raw": "물", "name": "물", "amount": "1", "unit": "컵", "alias_id": None},
            ]
        }
    )
    assembled = assemble_result(
        [["양파", "1", "개"], ["간장", "2", "t"], ["물", "1", "컵"]],
        parse_llm_response(mock_llm),
        index,
        {"alias_1", "alias_2"},
    )
    assert assembled["ingredients_normalized"] == [
        ["양파", "1", "개"],
        ["간장", "2", "큰술"],
        ["물", "1", "컵"],
    ]
    assert len(assembled["aliases_matched"]) == 2
    assert assembled["others_count"] == 1
    assert assembled["others_items"][0]["name"] == "물"
    assert "others" not in str(assembled["ingredients_normalized"]).lower()

    # resume 집합
    tmp = OUTPUT_CSV.parent / "_self_check_recipe_ingredient_alias.csv"
    try:
        if tmp.exists():
            tmp.unlink()
        ensure_output_header(tmp)
        append_result_row(
            tmp,
            {
                "RCP_SNO": 999,
                "CKG_NM": "테스트",
                "ingredients_raw": "[]",
                "aliases_matched": "[]",
                "ingredients_normalized": "[]",
                "others_count": 0,
                "others_items": "[]",
            },
        )
        assert load_processed_ids(tmp) == {999}
    finally:
        if tmp.exists():
            tmp.unlink()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="레시피 재료 정규화 + alias 매칭 LLM 배치")
    parser.add_argument("--input", default=str(RECIPE_FIX_CSV), help="입력 recipe_fix.csv")
    parser.add_argument("--output", default=str(OUTPUT_CSV), help="출력 recipe_ingredient_alias.csv")
    parser.add_argument("--alias", default=str(ALIAS_CSV), help="nodes_alias.csv 경로")
    parser.add_argument("--limit", type=int, default=None, help="처리 행 상한 (스모크·개발용)")
    parser.add_argument("--force", action="store_true", help="기존 출력 삭제 후 전체 재처리")
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _self_check()
    args = _parse_args()
    normalize_recipe_ingredients_by_llm(
        input_path=args.input,
        output_path=args.output,
        alias_path=args.alias,
        limit=args.limit,
        force=args.force,
    )
