import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from etl.load_to_neo4j.neo4j_connection import Neo4jSettings, load_settings, require_env


def test_load_settings_parses_env(monkeypatch):
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("NEO4J_DATABASE", "neo4j")

    settings = load_settings()

    assert isinstance(settings, Neo4jSettings)
    assert settings.uri == "bolt://localhost:7687"
    assert settings.user == "neo4j"
    assert settings.password == "secret"
    assert settings.database == "neo4j"


def test_require_env_raises_when_missing(monkeypatch):
    monkeypatch.delenv("NEO4J_URI", raising=False)
    with pytest.raises(ValueError, match="NEO4J_URI"):
        require_env("NEO4J_URI")
