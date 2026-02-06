"""Query execution commands."""

from pathlib import Path
from typing import Annotated

import typer

from kameleondb.cli.context import CLIContext
from kameleondb.cli.output import OutputFormatter

# Create query subcommand group
app = typer.Typer(help="Execute and validate SQL queries")


@app.command("run")
def query_run(
    ctx: typer.Context,
    sql: Annotated[
        str | None,
        typer.Argument(help="SQL query to execute"),
    ] = None,
    from_file: Annotated[
        str | None,
        typer.Option("--file", "-f", help="Load SQL from file"),
    ] = None,
    read_only: Annotated[
        bool,
        typer.Option("--read-only/--write", help="Only allow SELECT queries"),
    ] = True,
    entity_name: Annotated[
        str | None,
        typer.Option(
            "--entity", "-e", help="Primary entity being queried (enables optimization hints)"
        ),
    ] = None,
    show_metrics: Annotated[
        bool,
        typer.Option("--metrics/--no-metrics", help="Show performance metrics"),
    ] = True,
) -> None:
    """Execute a validated SQL query with optimization hints.

    Returns results with performance metrics and actionable optimization hints.
    This follows the agent-first principle - all operations provide intelligence inline.

    Examples:

        kameleondb query run "SELECT * FROM kdb_records LIMIT 10"
        kameleondb query run --file query.sql --entity Contact
        kameleondb query run "INSERT INTO ..." --write
        kameleondb query run "SELECT ..." --no-metrics  # Hide metrics
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        # Get SQL from argument or file
        if from_file:
            sql_content = Path(from_file).read_text()
        elif sql:
            sql_content = sql
        else:
            raise typer.BadParameter("Either provide SQL or use --file")

        # Execute query
        db = cli_ctx.get_db()
        result = db.execute_sql(
            sql_content,
            read_only=read_only,
            entity_name=entity_name,
            created_by="cli",
        )

        # Output results
        if cli_ctx.json_output:
            # JSON output includes everything
            formatter.print_data(
                {
                    "rows": result.rows,
                    "metrics": result.metrics.model_dump(),
                    "suggestions": [s.model_dump() for s in result.suggestions],
                    "warnings": result.warnings,
                }
            )
        else:
            # Human-readable output
            if result.rows:
                typer.echo(f"\nQuery returned {len(result.rows)} rows:\n")
                formatter.print_data(result.rows)
            else:
                typer.echo("Query executed successfully (no results)")

            # Show metrics if requested
            if show_metrics:
                typer.echo(f"\n⏱️  Execution time: {result.metrics.execution_time_ms:.2f}ms")
                if result.metrics.has_join:
                    typer.echo("🔗 Query includes JOIN operations")

            # Show optimization hints
            if result.suggestions:
                typer.echo("\n💡 Optimization Hints:")
                for suggestion in result.suggestions:
                    priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                        suggestion.priority, "ℹ️"
                    )
                    typer.echo(f"  {priority_emoji} {suggestion.reason}")
                    if suggestion.action:
                        typer.echo(f"     Action: {suggestion.action}")

            # Show warnings
            if result.warnings:
                typer.echo("\n⚠️  Warnings:")
                for warning in result.warnings:
                    typer.echo(f"  • {warning}")

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command("validate")
def query_validate(
    ctx: typer.Context,
    sql: Annotated[
        str | None,
        typer.Argument(help="SQL query to validate"),
    ] = None,
    from_file: Annotated[
        str | None,
        typer.Option("--file", "-f", help="Load SQL from file"),
    ] = None,
) -> None:
    """Validate SQL query without executing.

    Examples:

        kameleondb query validate "SELECT * FROM kdb_records"
        kameleondb query validate --file query.sql
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        # Get SQL from argument or file
        if from_file:
            sql_content = Path(from_file).read_text()
        elif sql:
            sql_content = sql
        else:
            raise typer.BadParameter("Either provide SQL or use --file")

        # Validate via QueryValidator (accessed through execute_sql with read_only)
        db = cli_ctx.get_db()

        # Try to execute with read_only to validate
        # (QueryValidator will check before execution)
        try:
            result = db.execute_sql(sql_content, read_only=True)
            formatter.print_success("Query is valid")

            # Show warnings if any
            if result.warnings:
                typer.echo("\n⚠️  Warnings:")
                for warning in result.warnings:
                    typer.echo(f"  • {warning}")
        except Exception as validation_error:
            # If validation fails, show the error
            formatter.print_error(validation_error)
            raise typer.Exit(code=1)

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()
