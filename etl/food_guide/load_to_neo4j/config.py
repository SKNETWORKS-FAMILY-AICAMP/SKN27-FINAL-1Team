from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

_FOOD_GUIDE_CSV_PATH = os.getenv("FOOD_GUIDE_CSV_PATH")
DEFAULT_FOOD_GUIDE_CSV = PROJECT_ROOT / _FOOD_GUIDE_CSV_PATH if _FOOD_GUIDE_CSV_PATH else None


@dataclass(frozen=True)
class Neo4jSettings:
    uri: str
    user: str
    password: str
    database: str


def require_env(key: str) -> str:
    value = os.getenv(key)
    if value is None or not value.strip():
        raise ValueError(f"Required environment variable is missing: {key}")
    return value.strip()


def load_settings() -> Neo4jSettings:
    return Neo4jSettings(
        uri=require_env("NEO4J_URI"),
        user=require_env("NEO4J_USER"),
        password=require_env("NEO4J_PASSWORD"),
        database=os.getenv("NEO4J_DATABASE", "neo4j").strip() or "neo4j",
    )
