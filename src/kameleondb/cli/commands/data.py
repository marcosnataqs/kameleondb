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


@app.command("batch-update")
def data_batch_update(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Entity name")],
    from_file: Annotated[
        str,
        typer.Option(
            "--from-file", "-f", help="JSONL file with updates (each line: {id, ...fields})"
        ),
    ],
) -> None:
    """Batch update multiple records from a JSONL file.

    Each line in the JSONL file should have an 'id' field and the fields to update.

    Examples:

        kameleondb data batch-update Customer --from-file updates.jsonl

        # updates.jsonl format:
        # {"id": "abc123", "tier": "gold", "score": 100}
        # {"id": "def456", "tier": "silver", "score": 85}
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()
        entity = db.entity(entity_name)

        # Read updates from JSONL file
        updates = read_jsonl_file(from_file)

        if not updates:
            formatter.print_error(Exception("No updates found in file"))
            raise typer.Exit(code=1)

        updated_count = 0
        errors: list[dict] = []

        for update in updates:
            record_id = update.pop("id", None)
            if not record_id:
                errors.append({"error": "Missing 'id' field", "data": update})
                continue

            try:
                entity.update(record_id, update)
                updated_count += 1
            except Exception as e:
                errors.append({"id": record_id, "error": str(e)})

        result = {
            "updated_count": updated_count,
            "error_count": len(errors),
            "total": len(updates),
        }
        if errors:
            result["errors"] = errors[:10]  # Show first 10 errors

        if errors:
            formatter.print_success(
                f"Updated {updated_count}/{len(updates)} records ({len(errors)} errors)",
                result,
            )
        else:
            formatter.print_success(
                f"Updated {updated_count} records",
                result,
            )

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("batch-delete")
def data_batch_delete(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Entity name")],
    record_ids: Annotated[
        list[str] | None,
        typer.Option("--id", help="Record ID to delete (repeatable)"),
    ] = None,
    from_file: Annotated[
        str | None,
        typer.Option("--from-file", "-f", help="File with IDs to delete (one per line)"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Batch delete multiple records.

    Examples:

        # Delete by IDs
        kameleondb data batch-delete Customer --id abc123 --id def456

        # Delete from file (one ID per line)
        kameleondb data batch-delete Customer --from-file ids_to_delete.txt --force
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()
        entity = db.entity(entity_name)

        # Collect IDs to delete
        all_ids: list[str] = list(record_ids) if record_ids else []

        if from_file:
            with open(from_file) as f:
                file_ids = [line.strip() for line in f if line.strip()]
                all_ids.extend(file_ids)

        if not all_ids:
            raise typer.BadParameter("No IDs provided. Use --id or --from-file")

        # Confirmation prompt
        if not force and not cli_ctx.json_output:
            confirm = typer.confirm(f"Delete {len(all_ids)} records from {entity_name}?")
            if not confirm:
                typer.echo("Cancelled.")
                raise typer.Exit(code=0)

        deleted_count = 0
        errors: list[dict] = []

        for record_id in all_ids:
            try:
                entity.delete(record_id)
                deleted_count += 1
            except Exception as e:
                errors.append({"id": record_id, "error": str(e)})

        result = {
            "deleted_count": deleted_count,
            "error_count": len(errors),
            "total": len(all_ids),
        }
        if errors:
            result["errors"] = errors[:10]

        if errors:
            formatter.print_success(
                f"Deleted {deleted_count}/{len(all_ids)} records ({len(errors)} errors)",
                result,
            )
        else:
            formatter.print_success(
                f"Deleted {deleted_count} records",
                result,
            )

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("stats")
def data_stats(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Entity name")],
) -> None:
    """Get statistics about entity data.

    Shows record counts, date ranges, and storage information.

    Examples:

        kameleondb data stats Customer
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()
        from sqlalchemy import text

        # Get entity info
        entity_info = db.describe_entity(entity_name)
        entity_def = db._schema_engine.get_entity(entity_name)

        if not entity_def:
            raise Exception(f"Entity not found: {entity_name}")

        # Get record counts and date ranges
        with db._connection.engine.connect() as conn:
            if entity_info.storage_mode == "dedicated" and entity_info.dedicated_table_name:
                table_name = entity_info.dedicated_table_name
                result = conn.execute(
                    text(
                        f"""
                    SELECT
                        COUNT(*) as total_records,
                        SUM(CASE WHEN is_deleted = false THEN 1 ELSE 0 END) as active_records,
                        SUM(CASE WHEN is_deleted = true THEN 1 ELSE 0 END) as deleted_records,
                        MIN(created_at) as earliest_created,
                        MAX(created_at) as latest_created,
                        MAX(updated_at) as last_modified
                    FROM "{table_name}"
                """
                    )
                ).fetchone()
            else:
                result = conn.execute(
                    text(
                        """
                    SELECT
                        COUNT(*) as total_records,
                        SUM(CASE WHEN is_deleted = 0 THEN 1 ELSE 0 END) as active_records,
                        SUM(CASE WHEN is_deleted = 1 THEN 1 ELSE 0 END) as deleted_records,
                        MIN(created_at) as earliest_created,
                        MAX(created_at) as latest_created,
                        MAX(updated_at) as last_modified
                    FROM kdb_records
                    WHERE entity_id = :entity_id
                """
                    ),
                    {"entity_id": entity_def.id},
                ).fetchone()

        stats_data = {
            "entity": entity_name,
            "total_records": result[0] or 0,
            "active_records": result[1] or 0,
            "deleted_records": result[2] or 0,
            "storage_mode": entity_info.storage_mode,
            "fields": len(entity_info.fields),
            "created_at_range": {
                "earliest": str(result[3]) if result[3] else None,
                "latest": str(result[4]) if result[4] else None,
            },
            "last_modified": str(result[5]) if result[5] else None,
        }

        if cli_ctx.json_output:
            formatter.print_data(stats_data)
        else:
            formatter.print_table(
                f"Data Stats for {entity_name}",
                [
                    {"Metric": "Total Records", "Value": stats_data["total_records"]},
                    {"Metric": "Active Records", "Value": stats_data["active_records"]},
                    {"Metric": "Deleted Records", "Value": stats_data["deleted_records"]},
                    {"Metric": "Storage Mode", "Value": stats_data["storage_mode"]},
                    {"Metric": "Fields", "Value": stats_data["fields"]},
                    {
                        "Metric": "Earliest Created",
                        "Value": stats_data["created_at_range"]["earliest"] or "N/A",
                    },
                    {
                        "Metric": "Latest Created",
                        "Value": stats_data["created_at_range"]["latest"] or "N/A",
                    },
                    {"Metric": "Last Modified", "Value": stats_data["last_modified"] or "N/A"},
                ],
                ["Metric", "Value"],
            )

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
