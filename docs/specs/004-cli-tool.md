# Spec 004: KameleonDB CLI Tool

**Status**: Draft  
**Created**: 2026-02-05  
**Target**: Pre-PyPI Launch (v0.1.0)

---

## Overview

Add a command-line interface (CLI) to KameleonDB using [Typer](https://typer.tiangolo.com/). The CLI enables developers and agents to interact with KameleonDB from the terminal without writing Python code.

## Goals

1. **Developer Experience**: Quick database exploration and prototyping
2. **Agent Integration**: Scriptable commands for shell-based agents
3. **Debugging**: Easy schema inspection and data queries
4. **Onboarding**: Lower barrier to entry for new users

## Non-Goals

- Full ORM replacement (use Python API for complex workflows)
- GUI or TUI (terminal UI) - keep it simple
- Real-time streaming (use MCP for that)

---

## Command Structure

```
kameleondb [OPTIONS] COMMAND [ARGS]
```

### Global Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--database` | `-d` | Database URL | `$KAMELEONDB_URL` or `sqlite:///./kameleondb.db` |
| `--echo` | `-e` | Echo SQL statements | `false` |
| `--json` | `-j` | Output as JSON (machine-readable) | `false` |
| `--help` | `-h` | Show help | - |
| `--version` | `-v` | Show version | - |

---

## Commands

### 1. Schema Commands (`schema`)

#### `schema list`
List all entities in the database.

```bash
kameleondb schema list
kameleondb schema list --json
```

**Output (table):**
```
Entities (3 total)
┌──────────┬─────────┬──────────┬─────────────┐
│ Name     │ Fields  │ Records  │ Storage     │
├──────────┼─────────┼──────────┼─────────────┤
│ Contact  │ 4       │ 150      │ shared      │
│ Order    │ 5       │ 1,203    │ dedicated   │
│ Product  │ 3       │ 45       │ shared      │
└──────────┴─────────┴──────────┴─────────────┘
```

#### `schema describe <entity>`
Show detailed entity information.

```bash
kameleondb schema describe Contact
kameleondb schema describe Contact --json
```

**Output:**
```
Entity: Contact
Storage: shared
Records: 150
Created: 2026-02-05 by agent-x

Fields (4)
┌────────────┬──────────┬──────────┬────────┬─────────┐
│ Name       │ Type     │ Required │ Unique │ Indexed │
├────────────┼──────────┼──────────┼────────┼─────────┤
│ name       │ string   │ ✓        │        │         │
│ email      │ string   │          │ ✓      │ ✓       │
│ phone      │ string   │          │        │         │
│ tier       │ string   │          │        │         │
└────────────┴──────────┴──────────┴────────┴─────────┘

Relationships (1)
┌───────────┬────────────┬──────────────┐
│ Name      │ To Entity  │ Type         │
├───────────┼────────────┼──────────────┤
│ orders    │ Order      │ one_to_many  │
└───────────┴────────────┴──────────────┘
```

#### `schema create <entity>`
Create a new entity with fields.

```bash
# Interactive (prompts for fields)
kameleondb schema create Contact

# Inline field definitions
kameleondb schema create Contact \
  --field "name:string:required" \
  --field "email:string:unique" \
  --field "phone:string" \
  --description "Customer contacts" \
  --created-by "cli-user"

# From JSON file
kameleondb schema create Contact --from-file contact-schema.json
```

**Field syntax**: `name:type[:modifier1][:modifier2]`
- Types: `string`, `text`, `int`, `float`, `bool`, `datetime`, `json`, `uuid`
- Modifiers: `required`, `unique`, `indexed`, `default=value`

#### `schema drop <entity>`
Drop an entity (soft delete).

```bash
kameleondb schema drop Contact
kameleondb schema drop Contact --reason "Migrating to new schema" --force
```

#### `schema add-field <entity> <field>`
Add a field to an existing entity.

```bash
kameleondb schema add-field Contact "linkedin_url:string"
kameleondb schema add-field Contact "score:int:indexed" --reason "Added for ranking"
```

#### `schema context`
Output LLM-ready schema context.

```bash
kameleondb schema context
kameleondb schema context --format markdown
kameleondb schema context > schema-context.md
```

---

### 2. Data Commands (`data`)

#### `data insert <entity> <json>`
Insert a record.

```bash
kameleondb data insert Contact '{"name": "John", "email": "john@example.com"}'

# From file
kameleondb data insert Contact --from-file contact.json

# Multiple records
kameleondb data insert Contact --from-file contacts.jsonl --batch
```

**Output:**
```
✓ Inserted record: 550e8400-e29b-41d4-a716-446655440000
```

#### `data get <entity> <id>`
Get a record by ID.

```bash
kameleondb data get Contact 550e8400-e29b-41d4-a716-446655440000
kameleondb data get Contact 550e8400 --json  # Prefix match
```

#### `data update <entity> <id> <json>`
Update a record.

```bash
kameleondb data update Contact 550e8400 '{"tier": "gold"}'
```

#### `data delete <entity> <id>`
Delete a record (soft delete).

```bash
kameleondb data delete Contact 550e8400
kameleondb data delete Contact 550e8400 --hard  # Permanent
```

#### `data list <entity>`
List records with optional filters.

```bash
kameleondb data list Contact
kameleondb data list Contact --limit 10 --offset 20
kameleondb data list Contact --where "tier = 'gold'"
```

---

### 3. Query Commands (`query`)

#### `query run <sql>`
Execute a validated SQL query.

```bash
kameleondb query run "SELECT * FROM kdb_records WHERE entity_id = '...'"
kameleondb query run --file query.sql
kameleondb query run "SELECT ..." --json
kameleondb query run "SELECT ..." --csv > results.csv
```

#### `query validate <sql>`
Validate SQL without executing.

```bash
kameleondb query validate "SELECT * FROM kdb_records"
```

**Output:**
```
✓ Query is valid
  Type: SELECT
  Tables: kdb_records
  Estimated cost: low
```

---

### 4. Storage Commands (`storage`)

#### `storage status <entity>`
Show storage mode and stats.

```bash
kameleondb storage status Contact
```

**Output:**
```
Entity: Contact
Storage Mode: shared
Table: kdb_records (shared)
Records: 150
Query Stats (24h):
  - Total queries: 47
  - Avg time: 12.3ms
  - Join frequency: 23
  
💡 Suggestion: Consider materializing - high join frequency detected
```

#### `storage materialize <entity>`
Migrate entity to dedicated table.

```bash
kameleondb storage materialize Contact
kameleondb storage materialize Contact --batch-size 1000
```

**Output:**
```
Materializing Contact...
  Creating table: kdb_contact
  Migrating records: 150/150 [████████████████] 100%
  Updating metadata...
✓ Materialized in 0.45s
  New table: kdb_contact
  Records migrated: 150
```

#### `storage dematerialize <entity>`
Migrate entity back to shared storage.

```bash
kameleondb storage dematerialize Contact
```

---

### 5. Admin Commands

#### `init`
Initialize a new database with KameleonDB tables.

```bash
kameleondb init
kameleondb init --database postgresql://localhost/mydb
```

#### `info`
Show database and connection info.

```bash
kameleondb info
```

**Output:**
```
KameleonDB v0.1.0
Database: postgresql://localhost/kameleondb
Dialect: PostgreSQL 15.2
Entities: 3
Total Records: 1,398
Storage: JSONB
```

#### `changelog`
Show schema changelog.

```bash
kameleondb changelog
kameleondb changelog --entity Contact
kameleondb changelog --limit 10
```

---

### 6. Shell Mode

#### `shell`
Interactive REPL for KameleonDB.

```bash
kameleondb shell
kameleondb shell --database sqlite:///./test.db
```

**Example session:**
```
KameleonDB Shell v0.1.0
Connected to: sqlite:///./kameleondb.db
Type 'help' for commands, 'exit' to quit.

kdb> schema list
Entities (2 total)
...

kdb> .entity Contact
Switched to entity: Contact

kdb[Contact]> insert {"name": "Jane", "email": "jane@example.com"}
✓ Inserted: 550e8400-e29b-41d4-a716-446655440001

kdb[Contact]> list --limit 5
...

kdb> exit
Goodbye!
```

**Shell commands:**
- `.entity <name>` - Switch context to entity
- `.sql` - Enter raw SQL mode
- `.json` - Toggle JSON output
- `.help` - Show help
- `.exit` / `Ctrl+D` - Exit

---

## Implementation Plan

### Phase 1: Core Structure (Day 1)
- [ ] Add `typer` to dependencies
- [ ] Create `src/kameleondb/cli/__init__.py`
- [ ] Create `src/kameleondb/cli/main.py` - entry point
- [ ] Create `src/kameleondb/cli/utils.py` - shared utilities (output formatting)
- [ ] Add `kameleondb` entry point to pyproject.toml
- [ ] Implement global options (--database, --json, --echo)

### Phase 2: Schema Commands (Day 1-2)
- [ ] `schema list`
- [ ] `schema describe`
- [ ] `schema create`
- [ ] `schema drop`
- [ ] `schema add-field`
- [ ] `schema context`

### Phase 3: Data Commands (Day 2)
- [ ] `data insert`
- [ ] `data get`
- [ ] `data update`
- [ ] `data delete`
- [ ] `data list`

### Phase 4: Query & Storage Commands (Day 2-3)
- [ ] `query run`
- [ ] `query validate`
- [ ] `storage status`
- [ ] `storage materialize`
- [ ] `storage dematerialize`

### Phase 5: Admin & Shell (Day 3)
- [ ] `init`
- [ ] `info`
- [ ] `changelog`
- [ ] `shell` (basic REPL)

### Phase 6: Polish (Day 3)
- [ ] Rich table output (using `rich` library)
- [ ] Progress bars for migrations
- [ ] Error handling and helpful messages
- [ ] Documentation and `--help` text
- [ ] Tests

---

## Dependencies

Add to `pyproject.toml`:

```toml
dependencies = [
    # ... existing
    "typer>=0.9.0",
    "rich>=13.0.0",  # Pretty tables and progress bars
]
```

Or as optional:

```toml
[project.optional-dependencies]
cli = [
    "typer>=0.9.0",
    "rich>=13.0.0",
]
```

**Entry point:**

```toml
[project.scripts]
kameleondb = "kameleondb.cli:main"
kameleondb-mcp = "kameleondb.integrations.mcp.server:main"
```

---

## File Structure

```
src/kameleondb/
├── cli/
│   ├── __init__.py       # Export main()
│   ├── main.py           # Typer app, global options
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── schema.py     # schema subcommands
│   │   ├── data.py       # data subcommands
│   │   ├── query.py      # query subcommands
│   │   ├── storage.py    # storage subcommands
│   │   └── admin.py      # init, info, changelog
│   ├── shell.py          # Interactive REPL
│   └── utils.py          # Output formatting, tables
```

---

## Example Usage Scenarios

### Scenario 1: Quick Prototyping
```bash
# Create a new database and entity
kameleondb init -d sqlite:///./prototype.db
kameleondb schema create Task \
  --field "title:string:required" \
  --field "done:bool" \
  --field "due_date:datetime"

# Add some data
kameleondb data insert Task '{"title": "Write CLI spec", "done": false}'
kameleondb data insert Task '{"title": "Implement CLI", "done": false}'

# Query
kameleondb data list Task
```

### Scenario 2: Production Debugging
```bash
# Check entity stats
kameleondb storage status Order -d $PROD_DB

# Get schema context for debugging
kameleondb schema context > /tmp/schema.md

# Run diagnostic query
kameleondb query run "SELECT COUNT(*) FROM kdb_records GROUP BY entity_id"
```

### Scenario 3: Migration
```bash
# Check before materializing
kameleondb storage status Contact

# Materialize for better performance
kameleondb storage materialize Contact --batch-size 5000

# Verify
kameleondb storage status Contact
```

---

## Success Criteria

1. All commands work with both PostgreSQL and SQLite
2. `--json` flag works on all commands (for scripting)
3. Helpful error messages with suggestions
4. Tab completion support (via Typer)
5. `--help` on every command with examples
6. Tests for all commands

---

## Open Questions

1. **Should `shell` be in v0.1.0?** Could defer to v0.2.0 to ship faster.
2. **Environment variable prefix?** `KAMELEONDB_URL` vs `KDB_DATABASE_URL`
3. **Config file support?** `.kameleondb.toml` for defaults?

---

## References

- [Typer Documentation](https://typer.tiangolo.com/)
- [Rich Documentation](https://rich.readthedocs.io/)
- [Click (Typer's foundation)](https://click.palletsprojects.com/)
