# Idea: OpenClaw Integration Guide

**Context:** KameleonDB is positioning as "the database for OpenClaw agents" but we don't have an official integration guide yet.

## What It Would Cover

### 1. Quick Start for OpenClaw Agents

```python
# In your OpenClaw skill
from kameleondb import KameleonDB

# Initialize (use sqlite for simplicity)
db = KameleonDB("sqlite:///agent-memory.db")

# Define entities for agent memory
db.create_entity("Contact", fields={"name": "string", "bio": "text"})
db.create_entity("Task", fields={
    "title": "string", 
    "status": "string",
    "due_date": "datetime"
})
db.create_entity("Insight", fields={
    "topic": "string",
    "summary": "text",
    "discovered_at": "datetime"
})

# Use in agent workflow
contact = db.entity("Contact")
contact_id = contact.insert({
    "name": "Marcos",
    "bio": "Creator of KameleonDB"
})
```

### 2. Common Agent Patterns

**Memory Management:**
- Contacts/People
- Tasks/Reminders
- Research/Insights
- Decisions (with context)
- Conversation history (structured)

**Query Examples:**
```python
# Find overdue tasks
db.query("SELECT * FROM kdb_records_with_entity WHERE entity_name = 'Task' AND status = 'pending'")

# Recent insights
insights = db.entity("Insight").list(limit=10)
```

### 3. Layer 2 for Agent Memory (when ready)

```python
# Enable semantic search on entities
db.create_entity("Research", 
    fields={"title": "string", "content": "text"},
    embed_fields=["title", "content"]  # Enable vector search
)

# Search semantically
results = db.search("Research", "agent memory patterns", mode="hybrid")
```

### 4. MCP Server Integration

Show how to expose KameleonDB via MCP for Claude Desktop / other MCP clients.

```bash
# Start MCP server
kameleondb mcp serve --database agent-memory.db --port 8080
```

### 5. Best Practices

- Use `created_by` for audit trail (agent name/session id)
- Structured data > markdown files for retrieval
- Layer 2 semantic search for "what did I learn about X?"
- M2M relationships for entity graphs (Contact ↔ Project)

## Where This Would Live

- `docs/guides/openclaw-integration.md` (official guide)
- Example skill: `examples/openclaw-agent-memory/` (working code)
- Blog post / demo video (marketing)

## Why Now?

1. **Layer 2 just landed** - semantic search makes agent memory way more powerful
2. **X research validated demand** - OpenClaw users struggling with file-based memory
3. **Early adopter window** - establish KameleonDB as THE solution before competitors

## Effort

- Guide: 2-3 hours
- Example skill: 2-4 hours
- Total: ~1 day of work for major positioning win

---

**Question for Marcos:** Should I draft the integration guide now, or wait until Layer 2 Phase 2 (CLI search commands) is done?
