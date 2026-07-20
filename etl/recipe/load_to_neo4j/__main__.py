from __future__ import annotations

import argparse
import logging

from .loader import _self_check, load_recipe_graph_to_neo4j

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load processed recipe graph CSV data into Neo4j.")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete existing Recipe/Reviewer nodes and their relationships before loading.",
    )
    return parser.parse_args()


def main() -> None:
    _self_check()
    args = _parse_args()
    result = load_recipe_graph_to_neo4j(clear=args.clear)
    logger.info(
        "Loaded Recipe=%d ColdStartUser=%d REQUIRES_INGREDIENT=%d REVIEWED=%d unresolved=%d",
        result.get("Recipe", 0),
        result.get("ColdStartUser", 0),
        result.get("REQUIRES_INGREDIENT", 0),
        result.get("REVIEWED", 0),
        result.get("UnlinkedIngredientOccurrences", 0),
    )


if __name__ == "__main__":
    main()
