"""Tool registry for agent access."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from kameleondb.tools.base import ToolDefinition, function_to_tool_definition

if TYPE_CHECKING:
    from kameleondb.core.engine import KameleonDB


class ToolRegistry:
    """Registry of tools for agent consumption.

    Provides methods to export KameleonDB operations as tools
    for various agent frameworks.
    """

    def __init__(self, db: KameleonDB) -> None:
        """Initialize tool registry.

        Args:
            db: KameleonDB instance
        """
        self._db = db
        self._tools: dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register default KameleonDB tools."""
        # Schema discovery tools
        self.register(
            name="kameleondb_describe",
            description="Get the full database schema including all entities and fields. "
            "Use this first to understand what data is available.",
            func=self._db.describe,
        )

        self.register(
            name="kameleondb_describe_entity",
            description="Get detailed information about a specific entity including all its fields. "
            "Returns entity details or an error with available entities if not found.",
            func=self._db.describe_entity,
        )

        # Entity management tools
        self.register(
            name="kameleondb_create_entity",
            description="Create a new entity type with fields. "
            "Use if_not_exists=True for idempotent operations (safe to call multiple times).",
            func=self._tool_create_entity,
        )

        self.register(
            name="kameleondb_list_entities",
            description="List all entity names in the database.",
            func=self._db.list_entities,
        )

    def _tool_create_entity(
        self,
        name: str,
        fields: list[dict[str, Any]] | None = None,
        description: str | None = None,
        created_by: str | None = None,
        if_not_exists: bool = True,
    ) -> dict[str, Any]:
        """Create a new entity (tool wrapper).

        Args:
            name: Entity name (PascalCase recommended)
            fields: List of field specifications
            description: Human-readable description
            created_by: Who/what created this entity
            if_not_exists: If True, skip if exists (idempotent)

        Returns:
            Entity info as dict
        """
        entity = self._db.create_entity(
            name=name,
            fields=fields,
            description=description,
            created_by=created_by,
            if_not_exists=if_not_exists,
        )
        return self._db.describe_entity(entity.name).model_dump()

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        description: str | None = None,
    ) -> ToolDefinition:
        """Register a tool.

        Args:
            name: Tool name
            func: Function to call
            description: Tool description

        Returns:
            Created ToolDefinition
        """
        tool = function_to_tool_definition(func, name=name, description=description)
        self._tools[name] = tool
        return tool

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool by name.

        Args:
            name: Tool name

        Returns:
            ToolDefinition or None
        """
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tool names.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def get_all(self) -> list[ToolDefinition]:
        """Get all registered tools.

        Returns:
            List of ToolDefinitions
        """
        return list(self._tools.values())

    def to_openai_format(self) -> list[dict[str, Any]]:
        """Export all tools in OpenAI function calling format.

        Returns:
            List of OpenAI tool definitions
        """
        return [tool.to_openai_format() for tool in self._tools.values()]

    def to_anthropic_format(self) -> list[dict[str, Any]]:
        """Export all tools in Anthropic Claude format.

        Returns:
            List of Anthropic tool definitions
        """
        return [tool.to_anthropic_format() for tool in self._tools.values()]

    def to_dict(self) -> list[dict[str, Any]]:
        """Export all tools as dicts.

        Returns:
            List of tool definitions as dicts
        """
        return [tool.to_dict() for tool in self._tools.values()]

    def register_entity_tools(self, entity_name: str) -> list[ToolDefinition]:
        """Register CRUD tools for a specific entity.

        Args:
            entity_name: Entity to create tools for

        Returns:
            List of created tools
        """
        entity = self._db.entity(entity_name)
        tools = []

        # Insert tool
        tool = self.register(
            name=f"kameleondb_{entity_name.lower()}_insert",
            func=entity.insert,
            description=f"Insert a new {entity_name} record.",
        )
        tools.append(tool)

        # Find tool
        tool = self.register(
            name=f"kameleondb_{entity_name.lower()}_find",
            func=entity.find,
            description=f"Find {entity_name} records matching filters.",
        )
        tools.append(tool)

        # Find by ID tool
        tool = self.register(
            name=f"kameleondb_{entity_name.lower()}_find_by_id",
            func=entity.find_by_id,
            description=f"Find a {entity_name} record by ID.",
        )
        tools.append(tool)

        # Update tool
        tool = self.register(
            name=f"kameleondb_{entity_name.lower()}_update",
            func=entity.update,
            description=f"Update a {entity_name} record.",
        )
        tools.append(tool)

        # Delete tool
        tool = self.register(
            name=f"kameleondb_{entity_name.lower()}_delete",
            func=entity.delete,
            description=f"Delete a {entity_name} record.",
        )
        tools.append(tool)

        # Add field tool
        tool = self.register(
            name=f"kameleondb_{entity_name.lower()}_add_field",
            func=entity.add_field,
            description=f"Add a new field to {entity_name}. Use if_not_exists=True for idempotent operations.",
        )
        tools.append(tool)

        return tools
