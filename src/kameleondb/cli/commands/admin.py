"""Admin and utility commands."""

from typing import Annotated

import typer

import kameleondb
from kameleondb.cli.context import CLIContext
from kameleondb.cli.output import OutputFormatter

# Create admin subcommand group
app = typer.Typer(help="Database administration and utilities")


@app.command()
def init(
    ctx: typer.Context,
) -> None:
    """Initialize a new database with KameleonDB tables.

    This command creates all necessary meta-tables (kdb_entity_definitions,
    kdb_field_definitions, kdb_records, etc.) in the database.

    Examples:

        kameleondb init
        kameleondb --database postgresql://localhost/mydb init
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        # Initialize database (connection initialization creates tables)
        cli_ctx.get_db()

        formatter.print_success(
            "Database initialized",
            {
                "database": cli_ctx.database_url,
                "version": kameleondb.__version__,
            },
        )

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command()
def info(
    ctx: typer.Context,
) -> None:
    """Show database and connection information.

    Examples:

        kameleondb info
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()

        # Get database info
        db.describe()
        entities = db.list_entities()

        # Count total records
        total_records_query = """
            SELECT COUNT(*) as count
            FROM kdb_records
            WHERE is_deleted = FALSE
        """
        result = db.execute_sql(total_records_query, read_only=True)
        total_records = result[0]["count"] if result else 0

        # Get dialect
        dialect = db._connection.dialect

        info_data = {
            "version": kameleondb.__version__,
            "database": cli_ctx.database_url,
            "dialect": dialect,
            "entities": len(entities),
            "total_records": total_records,
        }

        if cli_ctx.json_output:
            formatter.print_data(info_data)
        else:
            typer.echo(f"\nKameleonDB v{info_data['version']}")
            typer.echo(f"Database: {info_data['database']}")
            typer.echo(f"Dialect: {info_data['dialect']}")
            typer.echo(f"Entities: {info_data['entities']}")
            typer.echo(f"Total Records: {info_data['total_records']:,}")

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()


@app.command()
def changelog(
    ctx: typer.Context,
    entity_name: Annotated[
        str | None,
        typer.Option("--entity", "-e", help="Filter by entity name"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of entries"),
    ] = 20,
) -> None:
    """Show schema changelog.

    Examples:

        kameleondb changelog
        kameleondb changelog --entity Contact --limit 10
    """
    cli_ctx: CLIContext = ctx.obj
    formatter = OutputFormatter(cli_ctx.json_output)

    try:
        db = cli_ctx.get_db()

        # Get changelog
        entries = db.get_changelog(entity_name=entity_name, limit=limit)

        if cli_ctx.json_output:
            formatter.print_data(entries)
        else:
            if not entries:
                typer.echo("No changelog entries found")
            else:
                typer.echo(f"\nSchema Changelog ({len(entries)} entries):\n")
                for entry in entries:
                    typer.echo(f"[{entry['timestamp']}]")
                    typer.echo(f"  Operation: {entry['operation']}")
                    typer.echo(f"  Entity: {entry['entity_name']}")
                    if entry.get("field_name"):
                        typer.echo(f"  Field: {entry['field_name']}")
                    if entry.get("created_by"):
                        typer.echo(f"  By: {entry['created_by']}")
                    if entry.get("reason"):
                        typer.echo(f"  Reason: {entry['reason']}")
                    typer.echo("  ---")

    except Exception as e:
        formatter.print_error(e)
        raise typer.Exit(code=1)
    finally:
        cli_ctx.close()
