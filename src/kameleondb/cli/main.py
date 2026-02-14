"""KameleonDB CLI - Main entry point."""

from typing import Annotated

import typer

import kameleondb
from kameleondb.cli.context import CLIContext, get_database_url

# Create main Typer app
app = typer.Typer(
    name="kameleondb",
    help="KameleonDB CLI - The First Database Built for Agents",
    no_args_is_help=True,
)

# Store CLI context globally (will be set in callback)
state: dict[str, CLIContext] = {}


@app.callback()
def main_callback(
    ctx: typer.Context,
    database: Annotated[
        str | None,
        typer.Option(
            "--database",
            "-d",
            envvar="KAMELEONDB_URL",
            help="Database URL (PostgreSQL or SQLite)",
        ),
    ] = None,
    echo: Annotated[
        bool,
        typer.Option(
            "--echo",
            "-e",
            help="Echo SQL statements to console",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            "-j",
            help="Output as JSON (machine-readable)",
        ),
    ] = False,
) -> None:
    """Initialize CLI context with global options."""
    database_url = get_database_url(database)

    cli_ctx = CLIContext(
        database_url=database_url,
        echo=echo,
        json_output=json_output,
    )

    # Store in Typer context for command access
    ctx.obj = cli_ctx
    state["cli_ctx"] = cli_ctx


@app.command()
def version() -> None:
    """Show version information."""
    typer.echo(f"KameleonDB v{kameleondb.__version__}")


# Register command groups
from kameleondb.cli.commands import admin, data, query, schema, search, storage

app.add_typer(schema.app, name="schema")
app.add_typer(data.app, name="data")
app.add_typer(query.app, name="query")
app.add_typer(storage.app, name="storage")
app.add_typer(admin.app, name="admin")
app.add_typer(search.embeddings_app, name="embeddings")

# Register search as a standalone command (not a group)
app.command(name="search")(search.search_command)


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
