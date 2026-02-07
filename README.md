<p align="center">
  <img src="https://raw.githubusercontent.com/marcosnataqs/kameleondb/main/assets/kameleondb-logo.png" alt="KameleonDB Logo" width="350"/>
  <p align="center">
  <a href="https://pypi.org/project/kameleondb/"><img src="https://img.shields.io/pypi/v/kameleondb?color=blue" alt="PyPI version"></a>
  <a href="https://github.com/marcosnataqs/kameleondb/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/marcosnataqs/kameleondb/ci.yml?branch=main&label=tests" alt="Tests"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License: Apache 2.0"></a>
  <a href="https://github.com/marcosnataqs/kameleondb"><img src="https://img.shields.io/github/stars/marcosnataqs/kameleondb?style=social" alt="GitHub stars"></a>
  </p>
</p>

# KameleonDB

*Find the true color of your data.*

**The First Database Built for Agents to Own, Not Just Query**

Most databases let agents query data that humans structured. KameleonDB goes further: **agents own the entire data lifecycle**—from schema design to data ingestion to continuous evolution. You provide the goals and policies, agents build and manage the database.

Built on PostgreSQL (JSONB) or SQLite (JSON1) with schema-as-data storage, agents can restructure information on the fly without migrations, DDL, or human intervention.

## Philosophy: Agents as Data Engineers

In traditional databases, **humans are the data engineers**: they design schemas, write migrations, and structure data for agents to query.

KameleonDB **makes agents the data engineers**. Agents don't just consume data—they design the schema, ingest records, evolve structure, and reshape information as they reason about it. Humans shift from data architects to policy makers, defining what agents can do, not how to structure every field.

This is **schema-on-reason**: structure emerges from agent reasoning, not upfront human design. As agents learn more about the data, they adapt the schema to match their understanding.

**First Principles:**

1. **Radical Simplicity** — Perfection achieved by removing, not adding
2. **Agent-First Design** — APIs optimized for agent reasoning patterns
3. **Schema-on-Reason** — Schema emerges from reasoning, not upfront design
4. **Provenance & Auditability** — Every decision traceable
5. **Policy-Driven Governance** — Autonomy bounded by declarative policies
6. **Security by Design** — Zero-trust architecture
7. **Enterprise-Grade Reliability** — ACID guarantees and multi-tenancy

See [FIRST-PRINCIPLES.md](FIRST-PRINCIPLES.md) for detailed explanations and [AGENTS.md](AGENTS.md) for the complete agent-native design philosophy.

## Features

- **Dynamic Schema**: Create and modify entity fields at runtime without migrations
- **Multi-Database**: PostgreSQL (JSONB) and SQLite (JSON1) support
- **Agent-First Design**: Every operation is a tool for AI agents with JSON-serializable I/O
- **Self-Describing**: Agents can discover schema before querying
- **Idempotent Operations**: Safe for agents to call repeatedly
- **Audit Trail**: Track who made schema changes and why
- **Zero-Lock Evolution**: Schema changes are metadata-only, no table locks

## Installation

```bash
# Core only (SQLite works out of the box)
pip install kameleondb

# With PostgreSQL support
pip install kameleondb[postgresql]

# With MCP server
pip install kameleondb[mcp]

# For development
pip install kameleondb[dev,postgresql]

# Everything
pip install kameleondb[all]
```

**Database Requirements**:
- **SQLite**: 3.9+ with JSON1 extension (included in Python stdlib)
- **PostgreSQL**: 12+ with JSONB support

## Quick Start

### Option 1: MCP Server (Recommended for AI Agents)

The MCP (Model Context Protocol) server exposes KameleonDB as tools that AI agents can use directly.

**Installation:**
```bash
pip install kameleondb[mcp]
```

**Start the MCP server:**
```bash
# PostgreSQL
kameleondb-mcp --database postgresql://user:pass@localhost/kameleondb

# SQLite (for development)
kameleondb-mcp --database sqlite:///./kameleondb.db
```

**Configure in Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`):**
```json
{
  "mcpServers": {
    "kameleondb": {
      "command": "kameleondb-mcp",
      "args": ["--database", "postgresql://localhost/kameleondb"]
    }
  }
}
```

**Available MCP Tools:**
- `kameleondb_describe()` - Discover database schema
- `kameleondb_create_entity()` - Create new entity types
- `kameleondb_insert()` - Add records
- `kameleondb_execute_sql()` - Query with LLM-generated SQL
- `kameleondb_materialize_entity()` - Optimize storage for performance
- ...and 20+ more tools

See [MCP Documentation](https://modelcontextprotocol.io/) for client setup.

### Option 2: Command-Line Interface

**Installation:**
```bash
pip install kameleondb
```

**Initialize and create your first entity:**
```bash
# Initialize database
kameleondb init

# Create an entity
kameleondb schema create Contact \
  --field "name:string:required" \
  --field "email:string:unique" \
  --field "phone:string"

# Insert data (inline JSON)
kameleondb data insert Contact '{"name": "Alice", "email": "alice@example.com"}'

# Insert from file
kameleondb data insert Contact --from-file contact.json

# List records
kameleondb data list Contact

# Query with SQL
kameleondb query run "SELECT * FROM kdb_records WHERE entity_id='...' LIMIT 10"
```

**JSON output for scripting:**
```bash
kameleondb --json schema list | jq .
kameleondb --json data insert Contact '{"name":"Bob","email":"bob@example.com"}'
```

**Available Commands:**
- `schema` - Create, list, describe, modify entities
- `data` - Insert, get, update, delete, list records
- `query` - Execute and validate SQL
- `storage` - Materialize entities, check storage mode
- `admin` - Initialize, info, changelog

See `kameleondb --help` for full command reference.

### Option 3: Python API Integration

For developers integrating KameleonDB into Python applications:

```python
from kameleondb import KameleonDB

# Initialize with PostgreSQL
db = KameleonDB("postgresql://user:pass@localhost/kameleondb")

# Or use SQLite for development/testing
# db = KameleonDB("sqlite:///./kameleondb.db")

# Create an entity with fields
contacts = db.create_entity(
    name="Contact",
    fields=[
        {"name": "first_name", "type": "string", "required": True},
        {"name": "email", "type": "string", "unique": True},
    ],
    created_by="my-agent",
    if_not_exists=True,  # Idempotent - safe to call multiple times
)

# Add a field later (with reasoning for audit)
contacts.add_field(
    name="linkedin_url",
    field_type="string",
    created_by="enrichment-agent",
    reason="Found LinkedIn profiles in documents",
    if_not_exists=True,
)

# Insert data
contact_id = contacts.insert({
    "first_name": "John",
    "email": "john@example.com",
})

# Retrieve by ID
contact = contacts.find_by_id(contact_id)
print(contact)  # {"id": "...", "first_name": "John", "email": "john@example.com", ...}

# For complex queries, use SQL generation via schema context
context = db.get_schema_context()
# Use context with an LLM to generate SQL, then:
# results = db.execute_sql("SELECT ... FROM kdb_records WHERE ...")

# Discover schema (agents call this first)
schema = db.describe()
print(schema)
# {
#     "entities": {
#         "Contact": {
#             "fields": ["first_name", "email", "linkedin_url"],
#             ...
#         }
#     }
# }
```

**Tool Integration:**
```python
# Get all operations as tools for AI agents
tools = db.get_tools()

# Each tool has:
# - name: "kameleondb_create_entity"
# - description: Human-readable description
# - parameters: JSON Schema for inputs
# - function: Callable to execute
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for technical details.

## Agent Framework Integrations

### OpenClaw Skill

KameleonDB is available as an [OpenClaw](https://openclaw.ai) skill for seamless integration with OpenClaw agents. OpenClaw is an open-source agent framework that bridges messaging apps to AI agents with 700+ community skills.

**Installation:**
```bash
# Install KameleonDB
pip install kameleondb

# Set database URL
export KAMELEONDB_URL="sqlite:///./kameleondb.db"

# Initialize
kameleondb admin init

# Copy skill to OpenClaw (or install from ClawHub)
cp -r openclaw-skill ~/.openclaw/skills/kameleondb
```

**What OpenClaw Agents Can Do:**
- 🧠 **Remember information** across conversations (contacts, tasks, notes)
- 🔗 **Track entities and relationships** without planning schemas upfront
- 📚 **Build knowledge bases** that evolve as they learn
- 🌐 **Ingest external data** (APIs, web scraping, CSVs)
- 📊 **Query with SQL** using schema context for LLM-generated queries
- ⚡ **Self-optimize** with performance hints and materialization

**Key Features for Agents:**
- **Schema-on-Reason**: Start storing data immediately, add fields as you discover them
- **Agent Hints Pattern**: Query results include optimization suggestions with exact commands
- **Audit Trail**: Every schema change records why the agent made it
- **Zero Migrations**: Old records don't break when adding new fields

The skill provides the full CLI via `--json` flag, optimized for agent consumption. See [`openclaw-skill/SKILL.md`](openclaw-skill/SKILL.md) for usage examples and workflows.

**Coming Soon**: ClawHub listing for one-click installation 🦎

## Development

```bash
# Clone the repository
git clone https://github.com/marcosnataqs/kameleondb.git
cd kameleondb

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check src tests
mypy src/kameleondb

# Run pre-commit hooks
pre-commit install
pre-commit run --all-files
```

## Roadmap

- **v0.1**: Core schema engine ✅
- **v0.2**: Relationships + Hybrid Storage + Query Intelligence ✅
  - Relationship metadata (many-to-one, one-to-many, many-to-many)
  - Schema context for SQL generation
  - Query validation and execution
  - SQLite support
  - Hybrid storage (shared/dedicated modes)
  - Storage migration (materialize/dematerialize)
  - Query metrics and materialization suggestions
- **v0.3**: Relational queries + Many-to-many (planned)
  - Cross-entity queries with JOINs
  - Cascading operations
  - Many-to-many junction tables
- **v0.4**: Natural language queries (planned)
  - LLM-powered query generation
  - Query caching and optimization

See [docs/tasks/BACKLOG.md](docs/tasks/BACKLOG.md) for detailed roadmap.

## License

Apache 2.0 License - see [LICENSE](LICENSE) for details.
