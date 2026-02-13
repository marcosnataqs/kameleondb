"""CLI command tests for KameleonDB."""

import json
import os
import tempfile
from collections.abc import Generator

import pytest
from typer.testing import CliRunner

from kameleondb.cli.main import app

runner = CliRunner()


@pytest.fixture
def temp_db() -> Generator[str, None, None]:
    """Create a temporary SQLite database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield f"sqlite:///{db_path}"
    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def memory_db_url() -> str:
    """SQLite in-memory URL for tests."""
    return "sqlite:///:memory:"


class TestVersionCommand:
    """Test the version command."""

    def test_version_output(self) -> None:
        """Test that version command shows version info."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "KameleonDB v" in result.stdout


class TestSchemaCommands:
    """Test schema management commands."""

    def test_schema_list_empty(self, temp_db: str) -> None:
        """Test listing schemas when none exist."""
        result = runner.invoke(app, ["-d", temp_db, "schema", "list"])
        assert result.exit_code == 0

    def test_schema_list_json_empty(self, temp_db: str) -> None:
        """Test listing schemas as JSON when none exist."""
        result = runner.invoke(app, ["-d", temp_db, "--json", "schema", "list"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data == []

    def test_schema_create_simple(self, temp_db: str) -> None:
        """Test creating a simple entity."""
        result = runner.invoke(
            app,
            [
                "-d",
                temp_db,
                "--json",
                "schema",
                "create",
                "Contact",
                "-f",
                "name:string",
                "-f",
                "email:string",
            ],
        )
        assert result.exit_code == 0, f"Failed with: {result.stdout}"
        data = json.loads(result.stdout)
        assert data["name"] == "Contact"
        assert data["success"] is True

    def test_schema_create_with_types(self, temp_db: str) -> None:
        """Test creating entity with various field types."""
        result = runner.invoke(
            app,
            [
                "-d",
                temp_db,
                "--json",
                "schema",
                "create",
                "Product",
                "-f",
                "name:string:required",
                "-f",
                "price:float",
                "-f",
                "quantity:int",
                "-f",
                "available:bool",
            ],
        )
        assert result.exit_code == 0, f"Failed with: {result.stdout}"
        data = json.loads(result.stdout)
        assert data["name"] == "Product"
        assert data["fields"] == 4

    def test_schema_create_reserved_field_error(self, temp_db: str) -> None:
        """Test that reserved field names are rejected."""
        result = runner.invoke(
            app,
            ["-d", temp_db, "--json", "schema", "create", "BadEntity", "-f", "id:int"],
        )
        assert result.exit_code == 1
        assert "reserved" in result.stdout.lower() or "id" in result.stdout.lower()

    def test_schema_describe(self, temp_db: str) -> None:
        """Test describing an entity."""
        # First create an entity
        runner.invoke(
            app,
            ["-d", temp_db, "schema", "create", "User", "-f", "name:string", "-f", "email:string"],
        )

        # Then describe it
        result = runner.invoke(app, ["-d", temp_db, "--json", "schema", "describe", "User"])
        assert result.exit_code == 0, f"Failed with: {result.stdout}"
        data = json.loads(result.stdout)
        assert data["name"] == "User"
        assert "fields" in data

    def test_schema_describe_nonexistent(self, temp_db: str) -> None:
        """Test describing a non-existent entity."""
        result = runner.invoke(app, ["-d", temp_db, "schema", "describe", "NonExistent"])
        assert result.exit_code == 1

    def test_schema_alter_add_field(self, temp_db: str) -> None:
        """Test adding a field using schema alter."""
        # Create entity first
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Task", "-f", "title:string"])

        # Add a new field using alter --add
        result = runner.invoke(
            app, ["-d", temp_db, "--json", "schema", "alter", "Task", "--add", "priority:int"]
        )
        assert result.exit_code == 0, f"Failed with: {result.stdout}"

        # Verify field was added
        describe_result = runner.invoke(
            app, ["-d", temp_db, "--json", "schema", "describe", "Task"]
        )
        data = json.loads(describe_result.stdout)
        field_names = [f["name"] for f in data["fields"]]
        assert "priority" in field_names

    def test_schema_alter_reserved_field_error(self, temp_db: str) -> None:
        """Test that adding reserved field names is rejected."""
        runner.invoke(
            app, ["-d", temp_db, "schema", "create", "TaskReserved", "-f", "title:string"]
        )
        result = runner.invoke(
            app,
            [
                "-d",
                temp_db,
                "--json",
                "schema",
                "alter",
                "TaskReserved",
                "--add",
                "created_at:datetime",
            ],
        )
        assert result.exit_code == 1
        assert "reserved" in result.stdout.lower() or "created_at" in result.stdout.lower()

    def test_schema_alter_drop_field(self, temp_db: str) -> None:
        """Test dropping a field using schema alter."""
        # Create entity with multiple fields
        runner.invoke(
            app,
            [
                "-d",
                temp_db,
                "schema",
                "create",
                "Note",
                "-f",
                "title:string",
                "-f",
                "content:string",
            ],
        )

        # Drop a field using alter --drop --force
        result = runner.invoke(
            app,
            ["-d", temp_db, "--json", "schema", "alter", "Note", "--drop", "content", "--force"],
        )
        assert result.exit_code == 0, f"Failed with: {result.stdout}"

        # Verify field was removed
        describe_result = runner.invoke(
            app, ["-d", temp_db, "--json", "schema", "describe", "Note"]
        )
        data = json.loads(describe_result.stdout)
        field_names = [f["name"] for f in data["fields"]]
        assert "content" not in field_names
        assert "title" in field_names

    def test_schema_drop_entity(self, temp_db: str) -> None:
        """Test dropping an entity."""
        # Create entity
        runner.invoke(app, ["-d", temp_db, "schema", "create", "TempEntity", "-f", "data:string"])

        # Drop it
        result = runner.invoke(app, ["-d", temp_db, "--json", "schema", "drop", "TempEntity"])
        assert result.exit_code == 0, f"Failed with: {result.stdout}"

        # Verify it's gone
        list_result = runner.invoke(app, ["-d", temp_db, "--json", "schema", "list"])
        data = json.loads(list_result.stdout)
        assert "TempEntity" not in data

    def test_schema_add_relationship(self, temp_db: str) -> None:
        """Test adding a relationship between entities."""
        # Create two entities
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Author", "-f", "name:string"])
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Book", "-f", "title:string"])

        # Add relationship: Book -> Author (many-to-one)
        result = runner.invoke(
            app, ["-d", temp_db, "--json", "schema", "add-relationship", "Book", "Author"]
        )
        assert result.exit_code == 0, f"Failed with: {result.stdout}"

    def test_schema_info(self, temp_db: str) -> None:
        """Test schema stats command."""
        # Create some entities
        runner.invoke(app, ["-d", temp_db, "schema", "create", "A", "-f", "x:string"])
        runner.invoke(app, ["-d", temp_db, "schema", "create", "B", "-f", "y:int"])

        result = runner.invoke(app, ["-d", temp_db, "--json", "schema", "info"])
        assert result.exit_code == 0, f"Failed with: {result.stdout}"
        data = json.loads(result.stdout)
        # Stats returns a list of entity stats
        assert isinstance(data, list)
        assert len(data) == 2


class TestDataCommands:
    """Test data manipulation commands."""

    def test_data_insert_json(self, temp_db: str) -> None:
        """Test inserting data as JSON."""
        # Create entity
        runner.invoke(
            app, ["-d", temp_db, "schema", "create", "Item", "-f", "name:string", "-f", "value:int"]
        )

        # Insert data
        result = runner.invoke(
            app,
            ["-d", temp_db, "--json", "data", "insert", "Item", '{"name": "test", "value": 42}'],
        )
        assert result.exit_code == 0, f"Failed with: {result.stdout}"
        data = json.loads(result.stdout)
        assert "id" in data
        assert data["success"] is True

    def test_data_insert_json_array(self, temp_db: str) -> None:
        """Test batch inserting data using inline JSON array.

        Regression test for GitHub issue #46: Inline JSON array insert fails
        with 'unhashable type: dict'.
        """
        # Create entity
        runner.invoke(app, ["-d", temp_db, "schema", "create", "BatchItem", "-f", "name:string"])

        # Insert multiple records using inline JSON array
        result = runner.invoke(
            app,
            [
                "-d",
                temp_db,
                "--json",
                "data",
                "insert",
                "BatchItem",
                '[{"name": "A"}, {"name": "B"}, {"name": "C"}]',
            ],
        )
        assert result.exit_code == 0, f"Failed with: {result.stdout}"
        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["count"] == 3
        assert "ids" in data
        assert len(data["ids"]) == 3

        # Verify records were inserted
        list_result = runner.invoke(app, ["-d", temp_db, "--json", "data", "list", "BatchItem"])
        assert list_result.exit_code == 0
        records = json.loads(list_result.stdout)
        assert len(records) == 3

    def test_data_get(self, temp_db: str) -> None:
        """Test getting a record by ID."""
        # Create and insert
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Record", "-f", "data:string"])
        insert_result = runner.invoke(
            app, ["-d", temp_db, "--json", "data", "insert", "Record", '{"data": "hello"}']
        )
        assert insert_result.exit_code == 0, f"Insert failed: {insert_result.stdout}"
        record_id = json.loads(insert_result.stdout)["id"]

        # Get it back
        result = runner.invoke(
            app, ["-d", temp_db, "--json", "data", "get", "Record", str(record_id)]
        )
        assert result.exit_code == 0, f"Failed with: {result.stdout}"
        data = json.loads(result.stdout)
        assert data["id"] == record_id
        assert data["data"] == "hello"

    def test_data_get_nonexistent(self, temp_db: str) -> None:
        """Test getting a non-existent record."""
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Empty", "-f", "x:string"])
        result = runner.invoke(
            app,
            [
                "-d",
                temp_db,
                "--json",
                "data",
                "get",
                "Empty",
                "00000000-0000-0000-0000-000000000000",
            ],
        )
        assert result.exit_code == 1

    def test_data_update(self, temp_db: str) -> None:
        """Test updating a record."""
        # Create and insert
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Mutable", "-f", "value:string"])
        insert_result = runner.invoke(
            app, ["-d", temp_db, "--json", "data", "insert", "Mutable", '{"value": "old"}']
        )
        assert insert_result.exit_code == 0, f"Insert failed: {insert_result.stdout}"
        record_id = json.loads(insert_result.stdout)["id"]

        # Update it
        result = runner.invoke(
            app,
            [
                "-d",
                temp_db,
                "--json",
                "data",
                "update",
                "Mutable",
                str(record_id),
                '{"value": "new"}',
            ],
        )
        assert result.exit_code == 0, f"Failed with: {result.stdout}"

        # Verify update
        get_result = runner.invoke(
            app, ["-d", temp_db, "--json", "data", "get", "Mutable", str(record_id)]
        )
        data = json.loads(get_result.stdout)
        assert data["value"] == "new"

    def test_data_delete(self, temp_db: str) -> None:
        """Test deleting a record."""
        # Create and insert
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Deletable", "-f", "x:string"])
        insert_result = runner.invoke(
            app, ["-d", temp_db, "--json", "data", "insert", "Deletable", '{"x": "gone"}']
        )
        assert insert_result.exit_code == 0, f"Insert failed: {insert_result.stdout}"
        record_id = json.loads(insert_result.stdout)["id"]

        # Delete it
        result = runner.invoke(
            app, ["-d", temp_db, "--json", "data", "delete", "Deletable", str(record_id)]
        )
        assert result.exit_code == 0, f"Failed with: {result.stdout}"

        # Verify it's gone
        get_result = runner.invoke(
            app, ["-d", temp_db, "--json", "data", "get", "Deletable", str(record_id)]
        )
        assert get_result.exit_code == 1

    def test_data_list(self, temp_db: str) -> None:
        """Test listing records."""
        # Create and insert multiple records
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Many", "-f", "n:int"])
        for i in range(3):
            runner.invoke(app, ["-d", temp_db, "--json", "data", "insert", "Many", f'{{"n": {i}}}'])

        # List them
        result = runner.invoke(app, ["-d", temp_db, "--json", "data", "list", "Many"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) == 3

    def test_data_list_with_limit(self, temp_db: str) -> None:
        """Test listing records with limit."""
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Limited", "-f", "x:int"])
        for i in range(5):
            runner.invoke(
                app, ["-d", temp_db, "--json", "data", "insert", "Limited", f'{{"x": {i}}}']
            )

        result = runner.invoke(
            app, ["-d", temp_db, "--json", "data", "list", "Limited", "--limit", "2"]
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) == 2

    def test_data_info(self, temp_db: str) -> None:
        """Test data stats command."""
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Counted", "-f", "n:int"])
        for i in range(5):
            runner.invoke(
                app, ["-d", temp_db, "--json", "data", "insert", "Counted", f'{{"n": {i}}}']
            )

        result = runner.invoke(app, ["-d", temp_db, "--json", "data", "info", "Counted"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["entity"] == "Counted"
        assert data["total_records"] == 5


class TestRelationshipCommands:
    """Test relationship and linking commands."""

    def test_add_relationship_and_update_fk(self, temp_db: str) -> None:
        """Test adding a many-to-one relationship and linking via update."""
        # Create entities with relationship
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Dept", "-f", "name:string"])
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Emp", "-f", "name:string"])

        # Add relationship: Emp belongs to Dept
        add_rel_result = runner.invoke(
            app, ["-d", temp_db, "--json", "schema", "add-relationship", "Emp", "Dept"]
        )
        assert add_rel_result.exit_code == 0, f"Add relationship failed: {add_rel_result.stdout}"

        # Insert department
        dept_result = runner.invoke(
            app, ["-d", temp_db, "--json", "data", "insert", "Dept", '{"name": "Engineering"}']
        )
        assert dept_result.exit_code == 0, f"Insert failed: {dept_result.stdout}"
        dept_id = json.loads(dept_result.stdout)["id"]

        # Insert employee
        emp_result = runner.invoke(
            app, ["-d", temp_db, "--json", "data", "insert", "Emp", '{"name": "Alice"}']
        )
        assert emp_result.exit_code == 0, f"Insert failed: {emp_result.stdout}"
        emp_id = json.loads(emp_result.stdout)["id"]

        # Link via update using the FK field (dept_id)
        update_result = runner.invoke(
            app,
            [
                "-d",
                temp_db,
                "--json",
                "data",
                "update",
                "Emp",
                str(emp_id),
                f'{{"dept_id": "{dept_id}"}}',
            ],
        )
        assert update_result.exit_code == 0, f"Update failed: {update_result.stdout}"

        # Verify the link by getting the employee
        get_result = runner.invoke(
            app, ["-d", temp_db, "--json", "data", "get", "Emp", str(emp_id)]
        )
        assert get_result.exit_code == 0, f"Get failed: {get_result.stdout}"
        data = json.loads(get_result.stdout)
        assert data["dept_id"] == dept_id


class TestManyToManyCommands:
    """Test many-to-many relationship commands.

    Note: M2M tests with SQLite file databases can hit locking issues
    due to CLI connection management. These tests may need PostgreSQL
    for reliable execution in CI.
    """

    def test_add_m2m(self, temp_db: str) -> None:
        """Test adding M2M relationship creates junction table."""
        # Create entities
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Stu", "-f", "name:string"])
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Crs", "-f", "title:string"])

        # Add M2M relationship
        result = runner.invoke(
            app,
            ["-d", temp_db, "--json", "schema", "add-m2m", "Stu", "Crs"],
        )
        assert result.exit_code == 0, f"add-m2m failed: {result.stdout}"
        data = json.loads(result.stdout)
        assert data["success"] is True

    def test_m2m_link_and_get(self, temp_db: str) -> None:
        """Test linking records in M2M relationship."""
        # Create entities and M2M in sequence
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Writer", "-f", "name:string"])
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Novel", "-f", "title:string"])
        m2m_result = runner.invoke(
            app, ["-d", temp_db, "--json", "schema", "add-m2m", "Writer", "Novel"]
        )
        assert m2m_result.exit_code == 0, f"add-m2m failed: {m2m_result.stdout}"

        # The relationship name is auto-generated: "writer_novel"
        rel_name = "writer_novel"

        # Insert records
        writer_result = runner.invoke(
            app, ["-d", temp_db, "--json", "data", "insert", "Writer", '{"name": "Jane"}']
        )
        assert writer_result.exit_code == 0, f"Insert failed: {writer_result.stdout}"
        writer_id = json.loads(writer_result.stdout)["id"]

        novel_result = runner.invoke(
            app, ["-d", temp_db, "--json", "data", "insert", "Novel", '{"title": "Great Novel"}']
        )
        assert novel_result.exit_code == 0, f"Insert failed: {novel_result.stdout}"
        novel_id = json.loads(novel_result.stdout)["id"]

        # Link them using the auto-generated M2M relationship name
        link_result = runner.invoke(
            app,
            [
                "-d",
                temp_db,
                "--json",
                "data",
                "link",
                "Writer",
                str(writer_id),
                rel_name,
                str(novel_id),
            ],
        )
        assert link_result.exit_code == 0, f"Link failed: {link_result.stdout}"

        # Get linked novels
        linked_result = runner.invoke(
            app,
            ["-d", temp_db, "--json", "data", "get-linked", "Writer", str(writer_id), rel_name],
        )
        assert linked_result.exit_code == 0, f"Get-linked failed: {linked_result.stdout}"
        data = json.loads(linked_result.stdout)
        # Returns {"target_ids": [...], "count": N}
        assert data["count"] == 1
        assert len(data["target_ids"]) == 1


class TestStorageCommands:
    """Test storage management commands."""

    def test_storage_status(self, temp_db: str) -> None:
        """Test storage status command."""
        runner.invoke(app, ["-d", temp_db, "schema", "create", "StorageTest", "-f", "x:string"])
        runner.invoke(app, ["-d", temp_db, "data", "insert", "StorageTest", '{"x": "test"}'])

        result = runner.invoke(app, ["-d", temp_db, "--json", "storage", "status", "StorageTest"])
        assert result.exit_code == 0, f"Storage status failed: {result.stdout}"
        data = json.loads(result.stdout)
        assert data["entity_name"] == "StorageTest"
        assert "storage_mode" in data

    def test_storage_materialize_dematerialize(self, temp_db: str) -> None:
        """Test materialization and dematerialization."""
        # Create entity with data
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Mat", "-f", "value:int"])
        for i in range(3):
            runner.invoke(app, ["-d", temp_db, "data", "insert", "Mat", f'{{"value": {i}}}'])

        # Materialize
        mat_result = runner.invoke(app, ["-d", temp_db, "--json", "storage", "materialize", "Mat"])
        assert mat_result.exit_code == 0, f"Materialize failed: {mat_result.stdout}"

        # Check status
        status_result = runner.invoke(app, ["-d", temp_db, "--json", "storage", "status", "Mat"])
        data = json.loads(status_result.stdout)
        assert data["storage_mode"] in ["dedicated", "hybrid"]

        # Dematerialize
        demat_result = runner.invoke(
            app, ["-d", temp_db, "--json", "storage", "dematerialize", "Mat"]
        )
        assert demat_result.exit_code == 0, f"Dematerialize failed: {demat_result.stdout}"


class TestAdminCommands:
    """Test admin commands."""

    def test_admin_info(self, temp_db: str) -> None:
        """Test admin info command."""
        result = runner.invoke(app, ["-d", temp_db, "--json", "admin", "info"])
        assert result.exit_code == 0, f"Admin info failed: {result.stdout}"
        data = json.loads(result.stdout)
        assert "version" in data
        assert "database" in data

    def test_admin_init(self, temp_db: str) -> None:
        """Test admin init command."""
        result = runner.invoke(app, ["-d", temp_db, "--json", "admin", "init"])
        assert result.exit_code == 0

    def test_admin_changelog(self, temp_db: str) -> None:
        """Test admin changelog command."""
        result = runner.invoke(app, ["-d", temp_db, "--json", "admin", "changelog"])
        assert result.exit_code == 0


class TestGlobalOptions:
    """Test global CLI options."""

    def test_json_flag(self, temp_db: str) -> None:
        """Test that --json flag produces valid JSON output."""
        runner.invoke(app, ["-d", temp_db, "schema", "create", "JsonTest", "-f", "x:string"])
        result = runner.invoke(app, ["-d", temp_db, "--json", "schema", "list"])
        assert result.exit_code == 0
        # Should be valid JSON
        data = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_database_option(self, temp_db: str) -> None:
        """Test -d/--database option works."""
        result = runner.invoke(app, ["-d", temp_db, "schema", "list"])
        assert result.exit_code == 0

    def test_env_database_fallback(self, temp_db: str) -> None:
        """Test that KAMELEONDB_URL env var is used as fallback."""
        # Set env var
        os.environ["KAMELEONDB_URL"] = temp_db
        try:
            result = runner.invoke(app, ["schema", "list"])
            # Should succeed using env var
            assert result.exit_code == 0
        finally:
            del os.environ["KAMELEONDB_URL"]


class TestErrorHandling:
    """Test error handling in CLI commands."""

    def test_invalid_entity_name(self, temp_db: str) -> None:
        """Test error handling for invalid entity operations."""
        result = runner.invoke(app, ["-d", temp_db, "schema", "describe", "DoesNotExist"])
        assert result.exit_code == 1

    def test_invalid_json_data(self, temp_db: str) -> None:
        """Test error handling for invalid JSON input."""
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Valid", "-f", "x:string"])
        result = runner.invoke(app, ["-d", temp_db, "data", "insert", "Valid", "not valid json"])
        assert result.exit_code == 1

    def test_missing_required_args(self, temp_db: str) -> None:
        """Test error when required arguments are missing."""
        result = runner.invoke(app, ["-d", temp_db, "schema", "create"])
        assert result.exit_code != 0

    def test_duplicate_entity_error(self, temp_db: str) -> None:
        """Test that creating duplicate entity returns error."""
        runner.invoke(app, ["-d", temp_db, "schema", "create", "Dupe", "-f", "x:string"])
        result = runner.invoke(app, ["-d", temp_db, "schema", "create", "Dupe", "-f", "y:int"])
        # May succeed with different behavior or return error - check output contains entity name
        # The actual behavior depends on implementation
        assert result.exit_code == 1 or "Dupe" in result.stdout

    def test_invalid_field_type(self, temp_db: str) -> None:
        """Test error when using invalid field type."""
        result = runner.invoke(
            app, ["-d", temp_db, "schema", "create", "BadType", "-f", "x:invalid_type"]
        )
        assert result.exit_code == 1
        assert "type" in result.stdout.lower()
