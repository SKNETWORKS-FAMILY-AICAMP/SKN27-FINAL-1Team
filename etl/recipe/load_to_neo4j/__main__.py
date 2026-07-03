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
        "Loaded Recipe=%d Reviewer=%d WROTE_REVIEW=%d WROTE_COMMENT=%d",
        result.get("Recipe", 0),
        result.get("Reviewer", 0),
        result.get("WROTE_REVIEW", 0),
        result.get("WROTE_COMMENT", 0),
    )


if __name__ == "__main__":
    main()
