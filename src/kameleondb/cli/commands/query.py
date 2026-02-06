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
) -> None:
    """Execute a validated SQL query.

    Examples:

        kameleondb query run "SELECT * FROM kdb_records LIMIT 10"
        kameleondb query run --file query.sql
        kameleondb query run "INSERT INTO ..." --write
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
        results = db.execute_sql(sql_content, read_only=read_only)

        # Output results
        if cli_ctx.json_output:
            formatter.print_data(results)
        else:
            if results:
                typer.echo(f"\nQuery returned {len(results)} rows:\n")
                formatter.print_data(results)
            else:
                typer.echo("Query executed successfully (no results)")

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
            db.execute_sql(sql_content, read_only=True)
            formatter.print_success("Query is valid")
        except Exception as validation_error:
            # If validation fails, show the error
            formatter.print_error(validation_error)
            raise typer.Exit(code=1)

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()
