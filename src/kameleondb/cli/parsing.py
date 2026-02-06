"""Input parsing utilities for CLI commands."""

import json
from pathlib import Path
from typing import Any


def parse_field_spec(spec: str) -> dict[str, Any]:
    """Parse field specification string.

    Format: name:type[:modifier1][:modifier2]...

    Examples:
        "email:string:required:unique" → {"name": "email", "type": "string", "required": True, "unique": True}
        "score:int:indexed:default=0" → {"name": "score", "type": "int", "indexed": True, "default": 0}

    Args:
        spec: Field specification string

    Returns:
        Field dictionary with parsed attributes

    Raises:
        ValueError: If spec format is invalid
    """
    parts = spec.split(":")
    if len(parts) < 2:
        raise ValueError(f"Invalid field spec: '{spec}'. Expected format: name:type[:modifier]...")

    field: dict[str, Any] = {
        "name": parts[0],
        "type": parts[1],
        "required": False,
        "unique": False,
        "indexed": False,
    }

    # Parse modifiers
    for modifier in parts[2:]:
        if "=" in modifier:
            # Handle default=value
            key, value = modifier.split("=", 1)
            if key == "default":
                # Try to parse as JSON for proper type conversion
                try:
                    field["default"] = json.loads(value)
                except json.JSONDecodeError:
                    # If not valid JSON, use as string
                    field["default"] = value
        elif modifier in ("required", "unique", "indexed"):
            field[modifier] = True
        else:
            raise ValueError(
                f"Invalid modifier: '{modifier}'. "
                f"Supported: required, unique, indexed, default=value"
            )

    return field


def read_json_file(path: str) -> dict[str, Any]:
    """Read single JSON object from file.

    Args:
        path: Path to JSON file

    Returns:
        Parsed JSON object

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file contains invalid JSON
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with file_path.open("r") as f:
        return json.load(f)


def read_jsonl_file(path: str) -> list[dict[str, Any]]:
    """Read JSON Lines (JSONL) file.

    Each line should contain a separate JSON object.

    Args:
        path: Path to JSONL file

    Returns:
        List of parsed JSON objects

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If any line contains invalid JSON
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    records = []
    with file_path.open("r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise json.JSONDecodeError(
                    f"Invalid JSON on line {line_num}: {e.msg}",
                    e.doc,
                    e.pos,
                ) from e

    return records
