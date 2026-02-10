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


@app.command("link")
def data_link(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Source entity name")],
    record_id: Annotated[str, typer.Argument(help="Source record ID")],
    relationship_name: Annotated[str, typer.Argument(help="Relationship name")],
    target_id: Annotated[str, typer.Argument(help="Target record ID")],
    created_by: Annotated[
        str | None,
        typer.Option("--created-by", help="Creator identifier for audit trail"),
    ] = None,
) -> None:
    """Link two records in a many-to-many relationship.

    Examples:

        # Link a product to a tag
        kameleondb data link Product abc123 tags tag456

        # Link a student to a course
        kameleondb data link Student stu001 enrollments course101
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()
        entity = db.entity(entity_name)

        # Link records
        created = entity.link(
            relationship_name=relationship_name,
            record_id=record_id,
            target_id=target_id,
            created_by=created_by,
        )

        if created:
            formatter.print_success(
                f"Linked {entity_name}:{record_id} → {target_id}",
                {"source_id": record_id, "target_id": target_id, "relationship": relationship_name},
            )
        else:
            formatter.print_success(
                "Link already exists",
                {"source_id": record_id, "target_id": target_id, "relationship": relationship_name},
            )

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("unlink")
def data_unlink(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Source entity name")],
    record_id: Annotated[str, typer.Argument(help="Source record ID")],
    relationship_name: Annotated[str, typer.Argument(help="Relationship name")],
    target_id: Annotated[str, typer.Argument(help="Target record ID")],
) -> None:
    """Unlink two records in a many-to-many relationship.

    Examples:

        # Unlink a product from a tag
        kameleondb data unlink Product abc123 tags tag456
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()
        entity = db.entity(entity_name)

        # Unlink records
        removed = entity.unlink(
            relationship_name=relationship_name,
            record_id=record_id,
            target_id=target_id,
        )

        if removed:
            formatter.print_success(
                f"Unlinked {entity_name}:{record_id} → {target_id}",
                {"source_id": record_id, "target_id": target_id, "relationship": relationship_name},
            )
        else:
            formatter.print_success(
                "Link did not exist",
                {"source_id": record_id, "target_id": target_id, "relationship": relationship_name},
            )

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("link-many")
def data_link_many(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Source entity name")],
    record_id: Annotated[str, typer.Argument(help="Source record ID")],
    relationship_name: Annotated[str, typer.Argument(help="Relationship name")],
    target_ids: Annotated[
        list[str] | None,
        typer.Option("--target", "-t", help="Target record ID (repeatable)"),
    ] = None,
    from_file: Annotated[
        str | None,
        typer.Option("--from-file", "-f", help="Load target IDs from file (one per line)"),
    ] = None,
    created_by: Annotated[
        str | None,
        typer.Option("--created-by", help="Creator identifier for audit trail"),
    ] = None,
) -> None:
    """Link multiple target records to a source record.

    Examples:

        # Link product to multiple tags
        kameleondb data link-many Product abc123 tags -t tag1 -t tag2 -t tag3

        # Load target IDs from file
        kameleondb data link-many Product abc123 tags --from-file tag_ids.txt
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()
        entity = db.entity(entity_name)

        # Collect target IDs
        all_target_ids: list[str] = list(target_ids) if target_ids else []

        if from_file:
            with open(from_file) as f:
                file_ids = [line.strip() for line in f if line.strip()]
                all_target_ids.extend(file_ids)

        if not all_target_ids:
            raise typer.BadParameter("No target IDs provided. Use --target or --from-file")

        # Link all targets
        count = entity.link_many(
            relationship_name=relationship_name,
            record_id=record_id,
            target_ids=all_target_ids,
            created_by=created_by,
        )

        formatter.print_success(
            f"Linked {count} targets to {entity_name}:{record_id}",
            {"source_id": record_id, "linked_count": count, "total_provided": len(all_target_ids)},
        )

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("unlink-many")
def data_unlink_many(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Source entity name")],
    record_id: Annotated[str, typer.Argument(help="Source record ID")],
    relationship_name: Annotated[str, typer.Argument(help="Relationship name")],
    target_ids: Annotated[
        list[str] | None,
        typer.Option("--target", "-t", help="Target record ID (repeatable)"),
    ] = None,
    from_file: Annotated[
        str | None,
        typer.Option("--from-file", "-f", help="Load target IDs from file (one per line)"),
    ] = None,
    all_targets: Annotated[
        bool,
        typer.Option("--all", help="Unlink all targets for this relationship"),
    ] = False,
) -> None:
    """Unlink multiple target records from a source record.

    Examples:

        # Unlink specific targets
        kameleondb data unlink-many Product abc123 tags -t tag1 -t tag2

        # Unlink all targets
        kameleondb data unlink-many Product abc123 tags --all
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()
        entity = db.entity(entity_name)

        if all_targets:
            # Unlink all
            count = entity.unlink_all(
                relationship_name=relationship_name,
                record_id=record_id,
            )
            formatter.print_success(
                f"Unlinked all {count} targets from {entity_name}:{record_id}",
                {"source_id": record_id, "unlinked_count": count},
            )
        else:
            # Collect target IDs
            all_target_ids: list[str] = list(target_ids) if target_ids else []

            if from_file:
                with open(from_file) as f:
                    file_ids = [line.strip() for line in f if line.strip()]
                    all_target_ids.extend(file_ids)

            if not all_target_ids:
                raise typer.BadParameter(
                    "No target IDs provided. Use --target, --from-file, or --all"
                )

            # Unlink targets
            count = entity.unlink_many(
                relationship_name=relationship_name,
                record_id=record_id,
                target_ids=all_target_ids,
            )

            formatter.print_success(
                f"Unlinked {count} targets from {entity_name}:{record_id}",
                {
                    "source_id": record_id,
                    "unlinked_count": count,
                    "total_provided": len(all_target_ids),
                },
            )

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("get-linked")
def data_get_linked(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Source entity name")],
    record_id: Annotated[str, typer.Argument(help="Source record ID")],
    relationship_name: Annotated[str, typer.Argument(help="Relationship name")],
) -> None:
    """Get all linked target IDs for a many-to-many relationship.

    Examples:

        # Get all tags for a product
        kameleondb data get-linked Product abc123 tags
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()
        entity = db.entity(entity_name)

        # Get linked IDs
        linked_ids = entity.get_linked(
            relationship_name=relationship_name,
            record_id=record_id,
        )

        if cli_ctx.json_output:
            formatter.print_data({"target_ids": linked_ids, "count": len(linked_ids)})
        else:
            if linked_ids:
                typer.echo(f"\nLinked targets for {entity_name}:{record_id} ({len(linked_ids)}):\n")
                for tid in linked_ids:
                    typer.echo(f"  - {tid}")
            else:
                typer.echo(f"No linked targets for {entity_name}:{record_id}")

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

        if not entity_id_result.rows:
            raise Exception(f"Entity not found: {entity_name}")

        entity_id = entity_id_result.rows[0]["id"]

        # Query records
        sql = f"""
            SELECT id, data, created_at, updated_at
            FROM kdb_records
            WHERE entity_id = '{entity_id}' AND is_deleted = FALSE
            ORDER BY created_at DESC
            LIMIT {limit} OFFSET {offset}
        """
        result = db.execute_sql(sql, read_only=True)
        records = result.rows

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
