"""Tag system data loader — loads JSON tag schemas from configs/tags/."""

import json
from pathlib import Path
from typing import Any

# Resolve project root relative to this file (src/aicbc/utils/)
DEFAULT_TAGS_DIR = Path(__file__).resolve().parents[3] / "configs" / "tags"

# Known tag schema names
TAG_SCHEMA_NAMES = ["demographics", "behaviors", "psychologies", "scenarios"]


def _load_json(path: Path) -> dict[str, Any]:
    """Load and parse a JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_tag_schema(schema_name: str, tags_dir: Path | None = None) -> dict[str, Any]:
    """Load a single tag schema by name.

    Args:
        schema_name: One of 'demographics', 'behaviors', 'psychologies', 'scenarios'.
        tags_dir: Optional custom directory path. Defaults to configs/tags/.

    Returns:
        Parsed JSON schema as a dictionary.

    Raises:
        ValueError: If schema_name is unknown.
        FileNotFoundError: If the JSON file does not exist.
    """
    if schema_name not in TAG_SCHEMA_NAMES:
        raise ValueError(
            f"Unknown schema '{schema_name}'. "
            f"Must be one of: {TAG_SCHEMA_NAMES}"
        )

    directory = tags_dir or DEFAULT_TAGS_DIR
    file_path = directory / f"{schema_name}.json"

    if not file_path.exists():
        raise FileNotFoundError(f"Tag schema not found: {file_path}")

    return _load_json(file_path)


def load_all_tag_schemas(tags_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load all four tag schemas.

    Args:
        tags_dir: Optional custom directory path. Defaults to configs/tags/.

    Returns:
        Dictionary mapping schema_name -> parsed schema dict.
    """
    return {
        name: load_tag_schema(name, tags_dir=tags_dir)
        for name in TAG_SCHEMA_NAMES
    }


def get_dimension_options(
    schema_name: str,
    dimension_id: str,
    tags_dir: Path | None = None,
) -> list[str]:
    """Get the allowed options for a specific dimension.

    Args:
        schema_name: Tag schema name.
        dimension_id: Dimension identifier (e.g., 'age', 'price_sensitivity').
        tags_dir: Optional custom directory path.

    Returns:
        List of allowed option strings.

    Raises:
        ValueError: If dimension_id is not found in the schema.
    """
    schema = load_tag_schema(schema_name, tags_dir=tags_dir)
    for dim in schema.get("dimensions", []):
        if dim.get("id") == dimension_id:
            return dim.get("options", [])
    raise ValueError(
        f"Dimension '{dimension_id}' not found in schema '{schema_name}'"
    )


def list_dimensions(
    schema_name: str,
    tags_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """List all dimensions in a schema with their metadata.

    Args:
        schema_name: Tag schema name.
        tags_dir: Optional custom directory path.

    Returns:
        List of dimension metadata dictionaries.
    """
    schema = load_tag_schema(schema_name, tags_dir=tags_dir)
    return schema.get("dimensions", [])


def validate_tag_value(
    schema_name: str,
    dimension_id: str,
    value: str | list[str],
    tags_dir: Path | None = None,
) -> bool:
    """Validate a tag value against the schema.

    Args:
        schema_name: Tag schema name.
        dimension_id: Dimension identifier.
        value: Single value or list of values to validate.
        tags_dir: Optional custom directory path.

    Returns:
        True if valid, False otherwise.
    """
    try:
        options = get_dimension_options(schema_name, dimension_id, tags_dir=tags_dir)
    except (ValueError, FileNotFoundError):
        return False

    if not options:
        # Free-text dimensions (e.g., scenario narratives) accept any non-empty string
        if isinstance(value, str):
            return len(value.strip()) > 0
        return False

    if isinstance(value, list):
        return all(v in options for v in value)
    return value in options
