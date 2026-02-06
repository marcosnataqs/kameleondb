"""Storage management commands."""

from typing import Annotated

import typer

from kameleondb.cli.context import CLIContext
from kameleondb.cli.output import OutputFormatter, ProgressBarWrapper

# Create storage subcommand group
app = typer.Typer(help="Manage storage modes and materialization")


@app.command("status")
def storage_status(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Entity name")],
) -> None:
    """Show storage mode and performance stats.

    Examples:

        kameleondb storage status Contact
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()

        # Get entity info
        entity_info = db.describe_entity(entity_name)

        # Get entity stats (if available)
        try:
            stats = db.get_entity_stats(entity_name)
            stats_data = {
                "entity_name": entity_name,
                "storage_mode": entity_info.storage_mode,
                "record_count": entity_info.record_count or 0,
                "total_queries": stats.total_queries,
                "avg_execution_time_ms": stats.avg_execution_time_ms,
                "join_count_24h": stats.join_count_24h,
                "suggestion": stats.suggestion,
            }
        except Exception:
            # Stats not available
            stats_data = {
                "entity_name": entity_name,
                "storage_mode": entity_info.storage_mode,
                "record_count": entity_info.record_count or 0,
            }

        if cli_ctx.json_output:
            formatter.print_data(stats_data)
        else:
            typer.echo(f"\nEntity: {entity_name}")
            typer.echo(f"Storage Mode: {entity_info.storage_mode}")
            typer.echo(f"Records: {entity_info.record_count or 0:,}")

            if "total_queries" in stats_data:
                typer.echo("\nQuery Stats:")
                typer.echo(f"  Total queries: {stats_data['total_queries']}")
                typer.echo(f"  Avg execution time: {stats_data['avg_execution_time_ms']:.2f}ms")
                typer.echo(f"  Join frequency (24h): {stats_data['join_count_24h']}")

                if stats_data.get("suggestion"):
                    typer.echo(f"\n💡 {stats_data['suggestion']}")

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("materialize")
def storage_materialize(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Entity name")],
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", help="Number of records per batch"),
    ] = 1000,
    created_by: Annotated[
        str | None,
        typer.Option("--created-by", help="Creator identifier for audit trail"),
    ] = None,
    reason: Annotated[
        str | None,
        typer.Option("--reason", help="Reason for materialization"),
    ] = None,
) -> None:
    """Migrate entity from shared to dedicated storage.

    Creates a dedicated table with typed columns for the entity.

    Examples:

        kameleondb storage materialize Contact
        kameleondb storage materialize Contact --batch-size 5000
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()

        # Create progress bar wrapper
        with ProgressBarWrapper(cli_ctx.json_output) as progress:
            # Materialize with progress callback
            result = db.materialize_entity(
                name=entity_name,
                batch_size=batch_size,
                on_progress=progress.create_callback(entity_name),
                created_by=created_by,
                reason=reason,
            )

            if result["success"]:
                formatter.print_success(
                    f"Entity '{entity_name}' materialized",
                    {
                        "table": result["table_name"],
                        "records_migrated": result["records_migrated"],
                        "duration": f"{result['duration_seconds']:.2f}s",
                    },
                )
            else:
                error_msg = result.get("error", "Unknown error")
                formatter.print_error(Exception(f"Materialization failed: {error_msg}"))
                raise typer.Exit(code=1)

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("dematerialize")
def storage_dematerialize(
    ctx: typer.Context,
    entity_name: Annotated[str, typer.Argument(help="Entity name")],
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", help="Number of records per batch"),
    ] = 1000,
    created_by: Annotated[
        str | None,
        typer.Option("--created-by", help="Creator identifier for audit trail"),
    ] = None,
    reason: Annotated[
        str | None,
        typer.Option("--reason", help="Reason for dematerialization"),
    ] = None,
) -> None:
    """Migrate entity from dedicated back to shared storage.

    Moves data back to the shared kdb_records table.

    Examples:

        kameleondb storage dematerialize Contact
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()

        # Create progress bar wrapper
        with ProgressBarWrapper(cli_ctx.json_output) as progress:
            # Dematerialize with progress callback
            result = db.dematerialize_entity(
                name=entity_name,
                batch_size=batch_size,
                on_progress=progress.create_callback(entity_name),
                created_by=created_by,
                reason=reason,
            )

            if result["success"]:
                formatter.print_success(
                    f"Entity '{entity_name}' dematerialized",
                    {
                        "records_migrated": result["records_migrated"],
                        "duration": f"{result['duration_seconds']:.2f}s",
                    },
                )
            else:
                error_msg = result.get("error", "Unknown error")
                formatter.print_error(Exception(f"Dematerialization failed: {error_msg}"))
                raise typer.Exit(code=1)

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()
