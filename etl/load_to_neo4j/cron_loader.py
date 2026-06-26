from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from etl.food_guide.load_to_neo4j.config import DEFAULT_FOOD_GUIDE_CSV
from etl.food_guide.load_to_neo4j.loader import load_food_guide_to_neo4j

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reload food guide CSV into Neo4j when the CSV changes.")
    parser.add_argument("--csv", default=str(DEFAULT_FOOD_GUIDE_CSV))
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    last_mtime = None

    while True:
        mtime = Path(args.csv).stat().st_mtime
        if last_mtime is None or mtime > last_mtime:
            logger.info("Food guide CSV changed; loading to Neo4j")
            load_food_guide_to_neo4j(args.csv, clear=args.clear)
            last_mtime = mtime
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
