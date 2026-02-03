"""MCP (Model Context Protocol) integration for KameleonDB.

This module provides an MCP server that exposes KameleonDB operations
as tools for AI agents like Claude.

Example:
    # Run the MCP server
    python -m kameleondb.integrations.mcp.server --database postgresql://user:pass@localhost/db

    # Or via entry point (after pip install)
    kameleondb-mcp --database postgresql://user:pass@localhost/db
"""

from kameleondb.integrations.mcp.server import create_server, mcp

__all__ = ["mcp", "create_server"]
