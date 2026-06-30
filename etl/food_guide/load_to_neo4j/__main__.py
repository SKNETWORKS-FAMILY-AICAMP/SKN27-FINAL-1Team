from __future__ import annotations

import argparse
import logging

from .loader import (
    DEFAULT_FOOD_GUIDE_CSV,
    load_food_guide_to_neo4j,
    load_split_food_guide_to_neo4j,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load processed food guide CSV data into Neo4j.")
    parser.add_argument(
        "--csv",
        help="Path to processed food guide CSV. Required unless FOOD_GUIDE_CSV_PATH is set.",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete existing FoodGuide nodes and orphan FoodCategory nodes before loading.",
    )
    parser.add_argument(
        "--split-dir",
        help="Directory containing the node/relationship split CSV files.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.split_dir:
        result = load_split_food_guide_to_neo4j(args.split_dir, clear=args.clear)
        logger.info("Loaded split food guide graph: %s", result)
    else:
        csv_path = args.csv or DEFAULT_FOOD_GUIDE_CSV
        if not csv_path:
            raise SystemExit("Pass --csv or set FOOD_GUIDE_CSV_PATH. No default CSV is loaded.")
        result = load_food_guide_to_neo4j(csv_path, clear=args.clear)
        logger.info("Loaded FoodGuide=%d FoodCategory=%d", result["food_guides"], result["categories"])


if __name__ == "__main__":
    main()
