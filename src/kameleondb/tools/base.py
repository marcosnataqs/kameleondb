"""Base tool class for agent integrations."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, get_type_hints

from pydantic import BaseModel


class ToolDefinition(BaseModel):
    """Definition of a tool for agent consumption.

    Compatible with OpenAI, Claude, and LangChain tool formats.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    function: Callable[..., Any] | None = None

    model_config = {"arbitrary_types_allowed": True}

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_anthropic_format(self) -> dict[str, Any]:
        """Convert to Anthropic Claude tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to generic dict format."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


def python_type_to_json_schema(python_type: type) -> dict[str, Any]:
    """Convert Python type to JSON Schema type."""
    type_map: dict[type, dict[str, Any]] = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        list: {"type": "array"},
        dict: {"type": "object"},
        type(None): {"type": "null"},
    }

    # Handle Optional types
    origin = getattr(python_type, "__origin__", None)
    if origin is not None:
        args = getattr(python_type, "__args__", ())

        # Union type (Optional is Union[X, None])
        if origin.__name__ == "Union":
            # Check if it's Optional (has None in args)
            non_none_args = [a for a in args if a is not type(None)]
            if len(non_none_args) == 1:
                # It's Optional[X]
                return python_type_to_json_schema(non_none_args[0])
            # It's a real Union
            return {"anyOf": [python_type_to_json_schema(a) for a in args]}

        # List type
        if origin is list:
            if args:
                return {"type": "array", "items": python_type_to_json_schema(args[0])}
            return {"type": "array"}

        # Dict type
        if origin is dict:
            return {"type": "object"}

    return type_map.get(python_type, {"type": "string"})


def function_to_tool_definition(
    func: Callable[..., Any],
    name: str | None = None,
    description: str | None = None,
) -> ToolDefinition:
    """Convert a Python function to a ToolDefinition.

    Extracts parameter types and docstring to build JSON Schema.

    Args:
        func: Function to convert
        name: Override function name
        description: Override description (uses docstring if not provided)

    Returns:
        ToolDefinition for the function
    """
    tool_name = name or func.__name__
    tool_description = description or func.__doc__ or f"Execute {tool_name}"

    # Get function signature
    sig = inspect.signature(func)
    hints = get_type_hints(func) if hasattr(func, "__annotations__") else {}

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        # Skip self parameter
        if param_name == "self":
            continue

        # Get type hint
        param_type = hints.get(param_name, str)

        # Build parameter schema
        param_schema = python_type_to_json_schema(param_type)

        # Check if required (no default value)
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
        elif param.default is not None:
            param_schema["default"] = param.default

        properties[param_name] = param_schema

    parameters = {
        "type": "object",
        "properties": properties,
    }
    if required:
        parameters["required"] = required

    return ToolDefinition(
        name=tool_name,
        description=tool_description.strip(),
        parameters=parameters,
        function=func,
    )
