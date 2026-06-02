# tests/test_schema_visibility.py
from scripts import schema


def test_base_schema_allows_visibility_values():
    schemas = schema.load_schemas(vault_path=None)
    allowed = schemas["base"].get("allowed_values", {})
    assert allowed.get("visibility") == ["public", "private"]
