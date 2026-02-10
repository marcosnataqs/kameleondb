"""Schema management commands."""

from typing import Annotated

import typer

from kameleondb.cli.context import CLIContext
from kameleondb.cli.output import OutputFormatter
from kameleondb.cli.parsing import parse_field_spec, read_json_file

# Create schema subcommand group
app = typer.Typer(help="Manage entity schemas")


@app.command("list")
def schema_list(ctx: typer.Context) -> None:
    """List all entities in the database."""
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()
        entities = db.list_entities()

        if cli_ctx.json_output:
            formatter.print_data(entities)
        else:
            # Get full schema info for rich table
            db.describe()
            table_data = []
            for entity_name in entities:
                entity_info = db.describe_entity(entity_name)
                table_data.append(
                    {
                        "Name": entity_info.name,
                        "Fields": len(entity_info.fields),
                        "Records": entity_info.record_count or 0,
                        "Storage": entity_info.storage_mode,
                    }
                )

            formatter.print_table(
                f"Entities ({len(entities)} total)",
                table_data,
                ["Name", "Fields", "Records", "Storage"],
            )
    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("describe")
def schema_describe(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Entity name")],
) -> None:
    """Show detailed entity information."""
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()
        entity_info = db.describe_entity(entity_name)
        formatter.print_entity_info(entity_info)
    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("create")
def schema_create(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Entity name (e.g., Contact, Order)")],
    fields: Annotated[
        list[str] | None,
        typer.Option(
            "--field",
            "-f",
            help="Field spec: name:type[:modifier]. Can be repeated.",
        ),
    ] = None,
    from_file: Annotated[
        str | None,
        typer.Option(
            "--from-file",
            help="Load schema from JSON file",
        ),
    ] = None,
    description: Annotated[
        str | None,
        typer.Option("--description", "-d", help="Entity description"),
    ] = None,
    created_by: Annotated[
        str | None,
        typer.Option("--created-by", help="Creator identifier for audit trail"),
    ] = None,
) -> None:
    """Create a new entity with fields.

    Examples:

        # Inline fields
        kameleondb schema create Contact --field "name:string:required" --field "email:string:unique"

        # From JSON file
        kameleondb schema create Contact --from-file schema.json
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()

        # Parse field specs or load from file
        parsed_fields = []
        entity_name = name
        entity_description = description

        if from_file:
            # Load from JSON file
            schema_data = read_json_file(from_file)
            entity_name = schema_data.get("name", name)
            entity_description = schema_data.get("description", description)
            parsed_fields = schema_data.get("fields", [])
        elif fields:
            # Parse inline field specs
            parsed_fields = [parse_field_spec(spec) for spec in fields]

        # Create entity
        entity = db.create_entity(
            name=entity_name,
            fields=parsed_fields if parsed_fields else None,
            description=entity_description,
            created_by=created_by,
            if_not_exists=False,
        )

        formatter.print_success(
            f"Entity '{entity_name}' created",
            {
                "name": entity.name,
                "fields": len(parsed_fields) if parsed_fields else 0,
            },
        )
    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("drop")
def schema_drop(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Entity name")],
    reason: Annotated[
        str | None,
        typer.Option("--reason", help="Reason for dropping (audit trail)"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Skip confirmation prompt"),
    ] = False,
    created_by: Annotated[
        str | None,
        typer.Option("--created-by", help="Creator identifier for audit trail"),
    ] = None,
) -> None:
    """Drop an entity (soft delete)."""
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    # Confirmation prompt
    if not force and not cli_ctx.json_output:
        confirm = typer.confirm(f"Are you sure you want to drop entity '{entity_name}'?")
        if not confirm:
            typer.echo("Cancelled.")
            raise typer.Exit(code=0)

    try:
        db = cli_ctx.get_db()
        success = db.drop_entity(
            name=entity_name,
            created_by=created_by,
            reason=reason,
        )

        if success:
            formatter.print_success(f"Entity '{entity_name}' dropped")
        else:
            formatter.print_error(Exception(f"Failed to drop entity '{entity_name}'"))
            raise typer.Exit(code=1)
    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("add-field")
def schema_add_field(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Entity name")],
    field_spec: Annotated[
        str,
        typer.Argument(help="Field spec: name:type[:modifier]"),
    ],
    reason: Annotated[
        str | None,
        typer.Option("--reason", help="Reason for change (audit trail)"),
    ] = None,
    created_by: Annotated[
        str | None,
        typer.Option("--created-by", help="Creator identifier for audit trail"),
    ] = None,
) -> None:
    """Add a field to an existing entity.

    Examples:

        kameleondb schema add-field Contact "phone:string"
        kameleondb schema add-field Contact "score:int:indexed" --reason "Added for ranking"
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()
        entity = db.entity(entity_name)

        # Parse field spec
        field = parse_field_spec(field_spec)

        # Add field
        entity.add_field(
            name=field["name"],
            field_type=field.get("type", "string"),
            required=field.get("required", False),
            unique=field.get("unique", False),
            indexed=field.get("indexed", False),
            default=field.get("default"),
            created_by=created_by,
            reason=reason,
            if_not_exists=False,
        )

        formatter.print_success(
            f"Field '{field['name']}' added to '{entity_name}'",
            {"field": field["name"], "type": field["type"]},
        )
    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("drop-field")
def schema_drop_field(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Entity name")],
    field_name: Annotated[str, typer.Argument(help="Field name to drop")],
    reason: Annotated[
        str | None,
        typer.Option("--reason", help="Reason for change (audit trail)"),
    ] = None,
    created_by: Annotated[
        str | None,
        typer.Option("--created-by", help="Creator identifier for audit trail"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Drop a field from an existing entity (soft delete).

    The field is marked as inactive and no longer accessible through queries,
    but existing data in the JSONB column is preserved.

    Examples:

        kameleondb schema drop-field Contact phone_number
        kameleondb schema drop-field Contact legacy_field --reason "Field deprecated"
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    # Confirmation prompt
    if not force and not cli_ctx.json_output:
        confirm = typer.confirm(
            f"Are you sure you want to drop field '{field_name}' from '{entity_name}'?"
        )
        if not confirm:
            typer.echo("Cancelled.")
            raise typer.Exit(code=0)

    try:
        db = cli_ctx.get_db()
        entity = db.entity(entity_name)

        # Drop field
        entity.drop_field(
            name=field_name,
            created_by=created_by,
            reason=reason,
        )

        formatter.print_success(
            f"Field '{field_name}' dropped from '{entity_name}'",
            {"field": field_name, "entity": entity_name},
        )
    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("stats")
def schema_stats(
    ctx: typer.Context,
    entity_name: Annotated[
        str | None,
        typer.Argument(help="Entity name (optional, shows all if not specified)"),
    ] = None,
) -> None:
    """Get statistics about entities.

    Shows record counts, storage mode, query metrics, and optimization suggestions.

    Examples:

        # Stats for all entities
        kameleondb schema stats

        # Stats for specific entity
        kameleondb schema stats Contact
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()

        if entity_name:
            # Stats for specific entity
            stats = db.get_entity_stats(entity_name)
            data = stats.model_dump()

            if cli_ctx.json_output:
                formatter.print_data(data)
            else:
                # Rich table format
                formatter.print_table(
                    f"Stats for {entity_name}",
                    [
                        {"Metric": "Record Count", "Value": stats.record_count},
                        {"Metric": "Storage Mode", "Value": stats.storage_mode},
                        {"Metric": "Total Queries", "Value": stats.total_queries},
                        {
                            "Metric": "Avg Query Time (ms)",
                            "Value": f"{stats.avg_execution_time_ms:.2f}",
                        },
                        {
                            "Metric": "Max Query Time (ms)",
                            "Value": f"{stats.max_execution_time_ms:.2f}",
                        },
                        {"Metric": "Total Rows Returned", "Value": stats.total_rows_returned},
                        {"Metric": "JOINs (24h)", "Value": stats.join_count_24h},
                        {"Metric": "Suggestion", "Value": stats.suggestion or "None"},
                    ],
                    ["Metric", "Value"],
                )
        else:
            # Stats for all entities
            entities = db.list_entities()
            all_stats = []

            for name in entities:
                stats = db.get_entity_stats(name)
                all_stats.append(stats.model_dump())

            if cli_ctx.json_output:
                formatter.print_data(all_stats)
            else:
                table_data = [
                    {
                        "Entity": s["entity_name"],
                        "Records": s["record_count"],
                        "Storage": s["storage_mode"],
                        "Queries": s["total_queries"],
                        "Avg Time (ms)": f"{s['avg_execution_time_ms']:.2f}",
                    }
                    for s in all_stats
                ]
                formatter.print_table(
                    f"Entity Statistics ({len(entities)} entities)",
                    table_data,
                    ["Entity", "Records", "Storage", "Queries", "Avg Time (ms)"],
                )
    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("context")
def schema_context(
    ctx: typer.Context,
    entities: Annotated[
        list[str] | None,
        typer.Option("--entity", "-e", help="Specific entities (default: all)"),
    ] = None,
    include_examples: Annotated[
        bool,
        typer.Option("--examples/--no-examples", help="Include example queries"),
    ] = True,
    include_relationships: Annotated[
        bool,
        typer.Option("--relationships/--no-relationships", help="Include relationships"),
    ] = True,
) -> None:
    """Output LLM-ready schema context.

    This command generates comprehensive schema information optimized
    for LLM SQL query generation.
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(True)  # Always output as JSON

    try:
        db = cli_ctx.get_db()
        context = db.get_schema_context(
            entities=entities,
            include_examples=include_examples,
            include_relationships=include_relationships,
        )
        formatter.print_data(context)
    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()
