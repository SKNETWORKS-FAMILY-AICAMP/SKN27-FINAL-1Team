from __future__ import annotations

import argparse
import logging

from .loader import DEFAULT_FOOD_GUIDE_CSV, load_food_guide_to_neo4j

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load processed food guide CSV data into Neo4j.")
    parser.add_argument(
        "--csv",
        default=str(DEFAULT_FOOD_GUIDE_CSV),
        help="Path to processed food guide CSV.",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete existing FoodGuide nodes and orphan FoodCategory nodes before loading.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = load_food_guide_to_neo4j(args.csv, clear=args.clear)
    logger.info("Loaded FoodGuide=%d FoodCategory=%d", result["food_guides"], result["categories"])


if __name__ == "__main__":
    main()
