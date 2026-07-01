from __future__ import annotations

import argparse
import logging

from .loader import load_split_food_guide_to_neo4j

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load split food guide CSV data into Neo4j.")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete the existing food guide graph before loading.",
    )
    parser.add_argument(
        "--split-dir",
        default="storage/processed/food_guide",
        help="Directory containing the node/relationship split CSV files.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = load_split_food_guide_to_neo4j(args.split_dir, clear=args.clear)
    logger.info("Loaded split food guide graph: %s", result)


if __name__ == "__main__":
    main()
