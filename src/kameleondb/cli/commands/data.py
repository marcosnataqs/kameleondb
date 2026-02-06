"""Data CRUD commands."""

import json
from typing import Annotated

import typer

from kameleondb.cli.context import CLIContext
from kameleondb.cli.output import OutputFormatter
from kameleondb.cli.parsing import read_json_file, read_jsonl_file

# Create data subcommand group
app = typer.Typer(help="Manage entity data (CRUD operations)")


@app.command("insert")
def data_insert(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Entity name")],
    data_json: Annotated[
        str | None,
        typer.Argument(help="Record data as JSON string"),
    ] = None,
    from_file: Annotated[
        str | None,
        typer.Option("--from-file", "-f", help="Load data from JSON/JSONL file"),
    ] = None,
    batch: Annotated[
        bool,
        typer.Option("--batch", help="Batch insert from JSONL file (multiple records)"),
    ] = False,
    created_by: Annotated[
        str | None,
        typer.Option("--created-by", help="Creator identifier for audit trail"),
    ] = None,
) -> None:
    """Insert record(s) into an entity.

    Examples:

        # Inline JSON (single record)
        kameleondb data insert Contact '{"name": "John", "email": "john@example.com"}'

        # From JSON file (single record)
        kameleondb data insert Contact --from-file contact.json

        # Batch insert from JSONL file (multiple records)
        kameleondb data insert Contact --from-file contacts.jsonl --batch
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()
        entity = db.entity(entity_name)

        if from_file:
            # Load from file
            if batch:
                # Batch insert from JSONL
                records = read_jsonl_file(from_file)
                record_ids = entity.insert_many(records, created_by=created_by)
                formatter.print_success(
                    f"Inserted {len(record_ids)} records",
                    {"count": len(record_ids), "ids": record_ids[:5]},  # Show first 5
                )
            else:
                # Single record from JSON
                data = read_json_file(from_file)
                record_id = entity.insert(data, created_by=created_by)
                formatter.print_success(
                    "Inserted record",
                    {"id": record_id},
                )
        elif data_json:
            # Parse inline JSON
            data = json.loads(data_json)
            record_id = entity.insert(data, created_by=created_by)
            formatter.print_success(
                "Inserted record",
                {"id": record_id},
            )
        else:
            raise typer.BadParameter("Either provide data as JSON string or use --from-file")

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("get")
def data_get(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Entity name")],
    record_id: Annotated[str, typer.Argument(help="Record ID (UUID or prefix)")],
) -> None:
    """Get a record by ID.

    Examples:

        kameleondb data get Contact 550e8400-e29b-41d4-a716-446655440000
        kameleondb data get Contact 550e8400  # Prefix match
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()
        entity = db.entity(entity_name)
        record = entity.find_by_id(record_id)

        if record is None:
            formatter.print_error(Exception(f"Record not found: {record_id}"))
            raise typer.Exit(code=1)

        formatter.print_data(record)

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("update")
def data_update(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Entity name")],
    record_id: Annotated[str, typer.Argument(help="Record ID")],
    data_json: Annotated[str, typer.Argument(help="Update data as JSON string")],
) -> None:
    """Update a record.

    Examples:

        kameleondb data update Contact 550e8400 '{"tier": "gold"}'
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()
        entity = db.entity(entity_name)

        # Parse JSON
        data = json.loads(data_json)

        # Update record
        updated_record = entity.update(record_id, data)
        formatter.print_success(
            "Record updated",
            {"id": record_id},
        )

        if not cli_ctx.json_output:
            # Show updated record
            formatter.print_data(updated_record)

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("delete")
def data_delete(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Entity name")],
    record_id: Annotated[str, typer.Argument(help="Record ID")],
    hard: Annotated[
        bool,
        typer.Option("--hard", help="Permanent delete (default: soft delete)"),
    ] = False,
) -> None:
    """Delete a record.

    Examples:

        kameleondb data delete Contact 550e8400
        kameleondb data delete Contact 550e8400 --hard  # Permanent
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()
        entity = db.entity(entity_name)

        # TODO: hard delete not yet implemented in KameleonDB
        # For now, always soft delete
        success = entity.delete(record_id)

        if success:
            formatter.print_success(f"Record deleted: {record_id}")
        else:
            formatter.print_error(Exception(f"Failed to delete record: {record_id}"))
            raise typer.Exit(code=1)

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("list")
def data_list(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Entity name")],
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of records to return"),
    ] = 100,
    offset: Annotated[
        int,
        typer.Option("--offset", "-o", help="Number of records to skip"),
    ] = 0,
) -> None:
    """List records with pagination.

    Examples:

        kameleondb data list Contact
        kameleondb data list Contact --limit 10 --offset 20
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()

        # Use SQL query to list records with pagination
        db.describe_entity(entity_name)
        entity_id_query = f"SELECT id FROM kdb_entity_definitions WHERE name = '{entity_name}'"
        entity_id_result = db.execute_sql(entity_id_query, read_only=True)

        if not entity_id_result:
            raise Exception(f"Entity not found: {entity_name}")

        entity_id = entity_id_result[0]["id"]

        # Query records
        sql = f"""
            SELECT id, data, created_at, updated_at
            FROM kdb_records
            WHERE entity_id = '{entity_id}' AND is_deleted = FALSE
            ORDER BY created_at DESC
            LIMIT {limit} OFFSET {offset}
        """
        records = db.execute_sql(sql, read_only=True)

        if cli_ctx.json_output:
            formatter.print_data(records)
        else:
            if not records:
                typer.echo(f"No records found for {entity_name}")
            else:
                # Show records
                typer.echo(f"\nRecords for {entity_name} ({len(records)} shown):\n")
                for record in records:
                    typer.echo(f"ID: {record['id']}")
                    typer.echo(f"Data: {json.dumps(record['data'], indent=2)}")
                    typer.echo(f"Created: {record['created_at']}")
                    typer.echo("---")

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()
