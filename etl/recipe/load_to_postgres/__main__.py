"""`python -m etl.recipe.load_to_postgres` — 레시피 PostgreSQL 적재 CLI."""

from __future__ import annotations

import argparse
import logging

from .config import COOKING_STEPS_CSV, RECIPE_FIX_CSV
from .connection import PostgreDB
from .loader import load_recipes_to_postgres

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="레시피 CSV를 PostgreSQL에 적재합니다.")
    parser.add_argument(
        "--recipe-csv",
        type=str,
        default=str(RECIPE_FIX_CSV),
        help="전처리된 레시피 CSV 경로",
    )
    parser.add_argument(
        "--cooking-steps-csv",
        type=str,
        default=str(COOKING_STEPS_CSV),
        help="조리단계 CSV 경로",
    )
    parser.add_argument(
        "--test-conn",
        action="store_true",
        help="DB 연결만 확인하고 종료",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.test_conn:
        db = PostgreDB()
        logger.info(db.test_conn())
        return

    logger.info("레시피 적재 시작")
    logger.info("  recipe CSV: %s", args.recipe_csv)
    logger.info("  cooking steps CSV: %s", args.cooking_steps_csv)

    load_recipes_to_postgres(args.recipe_csv, args.cooking_steps_csv)


if __name__ == "__main__":
    main()
