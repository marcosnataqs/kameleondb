# KameleonDB CLI Reference

Complete command reference for the KameleonDB command-line interface.

## Global Options

```bash
kameleondb [OPTIONS] COMMAND [ARGS]...
```

| Option | Short | Description |
|--------|-------|-------------|
| `--database` | `-d` | Database URL (PostgreSQL or SQLite). Can also use `KAMELEONDB_URL` env var |
| `--echo` | `-e` | Echo SQL statements to console (debugging) |
| `--json` | `-j` | Output as JSON for machine-readable parsing |
| `--help` | | Show help and exit |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `KAMELEONDB_URL` | Default database URL (e.g., `sqlite:///data.db` or `postgresql://...`) |

---

## Commands Overview

| Command | Description |
|---------|-------------|
| `version` | Show version information |
| `schema` | Manage entity schemas |
| `data` | CRUD operations on entity records |
| `query` | Execute SQL queries |
| `storage` | Manage storage modes and materialization |
| `admin` | Database administration |

---

## Schema Commands

Manage entity definitions, fields, and relationships.

### `schema list`

List all entities in the database.

```bash
kameleondb schema list
```

### `schema describe`

Show detailed entity information including fields, relationships, and indexes.

```bash
kameleondb schema describe <entity_name>
```

### `schema create`

Create a new entity with fields.

```bash
kameleondb schema create <entity_name> [OPTIONS]

Options:
  --field, -f TEXT    Field definition (name:type[:constraints])
                      Types: string, text, integer, float, boolean, date, datetime, json
                      Constraints: required, unique, index
  --description TEXT  Entity description
```

**Examples:**

```bash
# Create entity with multiple fields
kameleondb schema create Contact \
  --field "name:string:required" \
  --field "email:string:unique" \
  --field "age:integer" \
  --field "notes:text"

# With description
kameleondb schema create Task \
  --field "title:string:required" \
  --field "status:string" \
  --field "due_date:date" \
  --description "Task tracking entity"
```

### `schema drop`

Drop an entity (soft delete).

```bash
kameleondb schema drop <entity_name> [--force]
```

### `schema alter`

Modify an entity's schema.

```bash
kameleondb schema alter <entity_name> [OPTIONS]

Options:
  --add TEXT       Add field (name:type[:constraints])
  --drop TEXT      Drop field by name
  --rename TEXT    Rename field (old_name:new_name)
```

**Examples:**

```bash
# Add a new field
kameleondb schema alter Contact --add "phone:string"

# Drop a field
kameleondb schema alter Contact --drop "fax"

# Rename a field
kameleondb schema alter Contact --rename "name:full_name"
```

### `schema add-relationship`

Create a many-to-one relationship between entities.

```bash
kameleondb schema add-relationship <source_entity> <target_entity> [OPTIONS]

Options:
  --field TEXT       Foreign key field name (default: <target>_id)
  --on-delete TEXT   Delete behavior: CASCADE, SET_NULL, RESTRICT (default: CASCADE)
```

**Example:**

```bash
# Contact belongs to Company
kameleondb schema add-relationship Contact Company --field company_id --on-delete CASCADE
```

### `schema add-m2m`

Create a many-to-many relationship between entities.

```bash
kameleondb schema add-m2m <source_entity> <target_entity> [OPTIONS]

Options:
  --name TEXT  Relationship name (default: auto-generated)
```

**Example:**

```bash
# Student can have many Courses, Course can have many Students
kameleondb schema add-m2m Student Course --name enrollment
```

### `schema info`

Get statistics about entities.

```bash
kameleondb schema info
```

### `schema context`

Output LLM-ready schema context for agent integration.

```bash
kameleondb schema context [--entity TEXT]
```

---

## Data Commands

CRUD operations on entity records.

### `data insert`

Insert record(s) into an entity.

```bash
kameleondb data insert <entity_name> [DATA_JSON] [OPTIONS]

Options:
  --from-file, -f TEXT  Load data from JSON/JSONL file
  --batch               Batch insert from JSONL file
  --created-by TEXT     Creator identifier for audit trail
```

**Examples:**

```bash
# Inline JSON (single record)
kameleondb data insert Contact '{"name": "John", "email": "john@example.com"}'

# From JSON file
kameleondb data insert Contact --from-file contact.json

# Batch insert from JSONL
kameleondb data insert Contact --from-file contacts.jsonl --batch

# Multiple records inline (JSON array)
kameleondb data insert Contact '[{"name": "Alice"}, {"name": "Bob"}]'
```

### `data get`

Get a record by ID (supports UUID prefix matching).

```bash
kameleondb data get <entity_name> <record_id>
```

### `data list`

List records with pagination.

```bash
kameleondb data list <entity_name> [OPTIONS]

Options:
  --limit INTEGER   Max records to return (default: 100)
  --offset INTEGER  Skip first N records (default: 0)
```

### `data update`

Update a record.

```bash
kameleondb data update <entity_name> <record_id> <update_json>
```

**Example:**

```bash
kameleondb data update Contact abc123 '{"status": "active"}'
```

### `data delete`

Delete a record (honors cascade rules).

```bash
kameleondb data delete <entity_name> <record_id> [OPTIONS]

Options:
  --force  Bypass RESTRICT checks (dangerous)
```

### `data batch-update`

Batch update multiple records from a JSONL file.

```bash
kameleondb data batch-update <entity_name> --from-file updates.jsonl
```

Each line should have `{"id": "...", ...fields to update...}`.

### `data batch-delete`

Batch delete multiple records.

```bash
kameleondb data batch-delete <entity_name> <id1> <id2> ... [OPTIONS]

Options:
  --from-file TEXT  File with record IDs (one per line)
  --force           Bypass RESTRICT checks
```

### `data info`

Get statistics about entity data.

```bash
kameleondb data info <entity_name>
```

### `data link`

Link records in a many-to-many relationship.

```bash
kameleondb data link <relationship_name> <source_id> <target_id>
```

**Example:**

```bash
kameleondb data link enrollment student-123 course-456
```

### `data unlink`

Unlink records in a many-to-many relationship.

```bash
kameleondb data unlink <relationship_name> <source_id> <target_id>
```

### `data get-linked`

Get all linked target IDs for a many-to-many relationship.

```bash
kameleondb data get-linked <relationship_name> <source_id>
```

---

## Query Commands

Execute SQL queries with validation and optimization.

### `query run`

Execute a validated SQL query.

```bash
kameleondb query run <sql_query> [OPTIONS]

Options:
  --limit INTEGER  Max rows to return (default: 100)
```

**Examples:**

```bash
# Simple query
kameleondb query run "SELECT * FROM kdb_records LIMIT 10"

# With JSON output
kameleondb --json query run "SELECT COUNT(*) as total FROM usr_Contact"
```

---

## Storage Commands

Manage storage modes for performance optimization.

### `storage status`

Show storage mode and performance stats for entities.

```bash
kameleondb storage status [--entity TEXT]
```

### `storage materialize`

Migrate entity from shared (kdb_records) to dedicated table storage. Improves query performance for large entities.

```bash
kameleondb storage materialize <entity_name>
```

### `storage dematerialize`

Migrate entity from dedicated back to shared storage.

```bash
kameleondb storage dematerialize <entity_name>
```

---

## Admin Commands

Database administration and utilities.

### `admin init`

Initialize a new database with KameleonDB system tables.

```bash
kameleondb admin init
```

### `admin info`

Show database and connection information.

```bash
kameleondb admin info
```

### `admin changelog`

Show schema changelog (all schema modifications).

```bash
kameleondb admin changelog [OPTIONS]

Options:
  --entity TEXT    Filter by entity name
  --limit INTEGER  Max entries to show (default: 50)
```

---

## JSON Output Mode

All commands support `--json` / `-j` for machine-readable output. The response structure varies by command but follows a consistent pattern:

**Success:**
```json
{
  "status": "success",
  "message": "Operation completed",
  "data": { ... }
}
```

**Error:**
```json
{
  "status": "error",
  "error": "Error message",
  "type": "ErrorType"
}
```

**List responses:**
```json
{
  "data": [...],
  "count": 10,
  "limit": 100,
  "offset": 0
}
```

---

## Usage with Agents

KameleonDB CLI is designed for agent integration. Best practices:

1. **Always use `--json`** for programmatic access
2. **Use `schema context`** to get LLM-ready schema descriptions
3. **Set `KAMELEONDB_URL`** environment variable to avoid passing `-d` every time
4. **Use UUID prefixes** - record IDs support prefix matching (e.g., `abc` matches `abc123-...`)

**Example agent workflow:**

```bash
# Get schema context for LLM
export KAMELEONDB_URL="sqlite:///agent-memory.db"
kameleondb --json schema context

# Insert a memory
kameleondb --json data insert Memory '{"content": "User prefers dark mode", "category": "preference"}'

# Query memories
kameleondb --json query run "SELECT * FROM usr_Memory WHERE data->>'category' = 'preference'"
```

---

## See Also

- [MCP Server](./MCP.md) - Model Context Protocol integration
- [Python API](./API.md) - Direct Python usage
- [Specs](./specs/) - Design specifications
