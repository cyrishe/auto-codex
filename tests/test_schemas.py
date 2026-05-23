from __future__ import annotations

import json
from pathlib import Path


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "codexflow" / "schemas"


def test_object_schemas_are_strict_for_codex_output() -> None:
    for schema_path in SCHEMA_DIR.glob("*.schema.json"):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        _assert_strict_objects(schema, path=schema_path.name)


def _assert_strict_objects(schema: dict, *, path: str) -> None:
    if schema.get("type") == "object":
        assert schema.get("additionalProperties") is False, path
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        assert set(properties) <= required, path
        for name, child in properties.items():
            _assert_strict_objects(child, path=f"{path}.{name}")
    elif schema.get("type") == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            _assert_strict_objects(items, path=f"{path}[]")

