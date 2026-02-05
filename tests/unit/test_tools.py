"""Tests for tool generation."""

from kameleondb import KameleonDB
from kameleondb.tools.base import ToolDefinition, function_to_tool_definition


class TestToolDefinition:
    """Tests for ToolDefinition class."""

    def test_to_openai_format(self):
        """Can convert to OpenAI format."""
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        )

        openai_format = tool.to_openai_format()
        assert openai_format["type"] == "function"
        assert openai_format["function"]["name"] == "test_tool"
        assert openai_format["function"]["description"] == "A test tool"

    def test_to_anthropic_format(self):
        """Can convert to Anthropic format."""
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
            },
        )

        anthropic_format = tool.to_anthropic_format()
        assert anthropic_format["name"] == "test_tool"
        assert anthropic_format["description"] == "A test tool"
        assert "input_schema" in anthropic_format

    def test_to_dict(self):
        """Can convert to generic dict."""
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object"},
        )

        data = tool.to_dict()
        assert data["name"] == "test_tool"
        assert data["description"] == "A test tool"


class TestFunctionToToolDefinition:
    """Tests for function_to_tool_definition."""

    def test_simple_function(self):
        """Can convert simple function."""

        def greet(name: str) -> str:
            """Greet a person."""
            return f"Hello, {name}!"

        tool = function_to_tool_definition(greet)
        assert tool.name == "greet"
        assert tool.description == "Greet a person."
        assert "name" in tool.parameters["properties"]
        assert tool.parameters["properties"]["name"]["type"] == "string"
        assert "name" in tool.parameters["required"]

    def test_function_with_defaults(self):
        """Parameters with defaults are optional."""

        def greet(name: str, greeting: str = "Hello") -> str:
            """Greet a person."""
            return f"{greeting}, {name}!"

        tool = function_to_tool_definition(greet)
        assert "name" in tool.parameters["required"]
        assert "greeting" not in tool.parameters.get("required", [])
        assert tool.parameters["properties"]["greeting"]["default"] == "Hello"

    def test_function_with_various_types(self):
        """Can handle various Python types."""

        def process(
            text: str,  # noqa: ARG001
            count: int,  # noqa: ARG001
            rate: float,  # noqa: ARG001
            active: bool,  # noqa: ARG001
        ) -> dict:
            """Process data."""
            return {}

        tool = function_to_tool_definition(process)
        props = tool.parameters["properties"]
        assert props["text"]["type"] == "string"
        assert props["count"]["type"] == "integer"
        assert props["rate"]["type"] == "number"
        assert props["active"]["type"] == "boolean"

    def test_custom_name_and_description(self):
        """Can override name and description."""

        def my_func():
            """Original description."""
            pass

        tool = function_to_tool_definition(
            my_func,
            name="custom_name",
            description="Custom description",
        )
        assert tool.name == "custom_name"
        assert tool.description == "Custom description"


class TestToolRegistry:
    """Tests for tool registry."""

    def test_default_tools_registered(self, memory_db: KameleonDB):
        """Default tools are registered."""
        tools = memory_db.get_tools()
        tool_names = [t.name for t in tools]
        assert "kameleondb_describe" in tool_names
        assert "kameleondb_describe_entity" in tool_names
        assert "kameleondb_create_entity" in tool_names
        assert "kameleondb_list_entities" in tool_names

    def test_list_tools(self, memory_db: KameleonDB):
        """Can list tool names."""
        tool_names = memory_db.tools.list_tools()
        assert isinstance(tool_names, list)
        assert len(tool_names) > 0

    def test_get_tool(self, memory_db: KameleonDB):
        """Can get a specific tool."""
        tool = memory_db.tools.get("kameleondb_describe")
        assert tool is not None
        assert tool.name == "kameleondb_describe"

    def test_get_nonexistent_tool(self, memory_db: KameleonDB):
        """Getting nonexistent tool returns None."""
        tool = memory_db.tools.get("nonexistent")
        assert tool is None

    def test_export_openai_format(self, memory_db: KameleonDB):
        """Can export all tools in OpenAI format."""
        tools = memory_db.tools.to_openai_format()
        assert isinstance(tools, list)
        assert len(tools) > 0
        assert all(t["type"] == "function" for t in tools)

    def test_export_anthropic_format(self, memory_db: KameleonDB):
        """Can export all tools in Anthropic format."""
        tools = memory_db.tools.to_anthropic_format()
        assert isinstance(tools, list)
        assert len(tools) > 0
        assert all("input_schema" in t for t in tools)

    def test_register_entity_tools(self, memory_db: KameleonDB):
        """Can register CRUD tools for an entity."""
        memory_db.create_entity("Contact", fields=[{"name": "email", "type": "string"}])
        tools = memory_db.tools.register_entity_tools("Contact")

        tool_names = [t.name for t in tools]
        assert "kameleondb_contact_insert" in tool_names
        assert "kameleondb_contact_find_by_id" in tool_names
        assert "kameleondb_contact_update" in tool_names
        assert "kameleondb_contact_delete" in tool_names
        assert "kameleondb_contact_add_field" in tool_names

    def test_register_custom_tool(self, memory_db: KameleonDB):
        """Can register custom tools."""

        def my_custom_action(value: str) -> str:
            """Do something custom."""
            return value.upper()

        tool = memory_db.tools.register(
            name="my_custom_action",
            func=my_custom_action,
            description="Custom action description",
        )

        assert tool.name == "my_custom_action"
        assert "my_custom_action" in memory_db.tools.list_tools()
