"""CLI commands for semantic search and embeddings."""

import contextlib
import json
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from kameleondb.cli.context import CLIContext

# Embeddings subcommand group
embeddings_app = typer.Typer(help="Embeddings management")

console = Console()


# Search command (registered as standalone in main.py)
def search_command(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Search query text")],
    entity: Annotated[str | None, typer.Option("--entity", "-e", help="Entity name to search")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Maximum results to return")] = 10,
    min_score: Annotated[
        float | None, typer.Option("--threshold", "-t", help="Minimum relevance score")
    ] = None,
    where: Annotated[
        str | None, typer.Option("--where", "-w", help="Structured filters as JSON (e.g., '{\"status\": \"open\"}')")
    ] = None,
) -> None:
    """Search records using semantic search with optional filters.

    Examples:
        kameleondb search "customer complaint about shipping"
        kameleondb search "email address" --entity Contact --limit 5
        kameleondb search "Python tutorial" --threshold 0.7 --json
        kameleondb search "bug report" --entity Ticket --where '{"status": "open", "priority": "high"}'
    """
    try:
        cli_ctx: CLIContext = ctx.obj
        db = cli_ctx.get_db()

        # Validate embeddings enabled
        if not db._embeddings_enabled:
            console.print(
                "[red]Error:[/red] Embeddings not enabled. "
                "Set KAMELEONDB_EMBEDDINGS=1 when creating the database."
            )
            raise typer.Exit(1)

        # Parse where filter if provided
        where_dict = None
        if where:
            try:
                where_dict = json.loads(where)
                if not isinstance(where_dict, dict):
                    console.print("[red]Error:[/red] --where must be a JSON object")
                    raise typer.Exit(1)
            except json.JSONDecodeError as e:
                console.print(f"[red]Error:[/red] Invalid JSON in --where: {e}")
                raise typer.Exit(1)

        # Execute search
        results = db.search(
            query=query,
            entity=entity,
            limit=limit,
            min_score=min_score,
            where=where_dict,
        )

        if cli_ctx.json_output:
            output = {
                "query": query,
                "entity": entity,
                "where": where_dict,
                "count": len(results),
                "results": results,
            }
            console.print(json.dumps(output, indent=2))
        else:
            if not results:
                filter_info = f" with filters {where_dict}" if where_dict else ""
                console.print(f"[yellow]No results found for:[/yellow] {query}{filter_info}")
                return

            title = f"Search Results: {query}"
            if where_dict:
                title += f" [dim](filtered: {where_dict})[/dim]"
            table = Table(title=title)
            table.add_column("Entity", style="cyan")
            table.add_column("ID", style="dim")
            table.add_column("Score", style="green")
            table.add_column("Preview", style="white", max_width=60)

            for r in results:
                # Parse data if it's a JSON string
                data = r["data"]
                if isinstance(data, str):
                    with contextlib.suppress(json.JSONDecodeError):
                        data = json.loads(data)

                # Build preview from matched_text or first field
                preview = r.get("matched_text", "")[:80]
                if not preview and isinstance(data, dict):
                    preview = str(list(data.values())[0])[:80] if data else ""

                table.add_row(
                    r["entity"],
                    r["id"][:12] + "...",
                    f"{r['score']:.3f}",
                    preview,
                )

            console.print(table)
            console.print(f"\n[dim]Showing {len(results)} results[/dim]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@embeddings_app.command("status")
def embeddings_status(
    ctx: typer.Context,
) -> None:
    """Show embedding configuration and indexing status.

    Examples:
        kameleondb embeddings status
        kameleondb embeddings status --json
    """
    try:
        cli_ctx: CLIContext = ctx.obj
        db = cli_ctx.get_db()

        if not db._embeddings_enabled:
            console.print("[yellow]Embeddings:[/yellow] disabled")
            if cli_ctx.json_output:
                console.print(json.dumps({"enabled": False}))
            raise typer.Exit(0)

        # Get provider info
        provider_info = {
            "enabled": True,
            "provider": "unknown",
            "model": "unknown",
            "dimensions": 0,
        }

        if db._search_engine and db._search_engine._embedding_provider:
            provider = db._search_engine._embedding_provider
            provider_info["model"] = getattr(provider, "model_name", "unknown")
            provider_info["dimensions"] = getattr(provider, "dimensions", 0)
            # Detect provider type
            provider_class = provider.__class__.__name__
            if "FastEmbed" in provider_class:
                provider_info["provider"] = "fastembed"
            elif "OpenAI" in provider_class:
                provider_info["provider"] = "openai"

        # Get indexing status
        status = db.embedding_status()
        indexed_entities = [
            {
                "entity": s["entity"],
                "indexed": s["indexed"],
                "pending": s.get("pending", 0),
                "last_updated": s.get("last_updated"),
            }
            for s in status
        ]

        if cli_ctx.json_output:
            output = {**provider_info, "indexed_entities": indexed_entities}
            console.print(json.dumps(output, indent=2))
        else:
            console.print("[green]✓[/green] Embeddings: enabled")
            console.print(f"  Provider: {provider_info['provider']}")
            console.print(f"  Model: {provider_info['model']}")
            console.print(f"  Dimensions: {provider_info['dimensions']}")
            console.print()

            if indexed_entities:
                table = Table(title="Indexed Entities")
                table.add_column("Entity", style="cyan")
                table.add_column("Indexed", style="green", justify="right")
                table.add_column("Pending", style="yellow", justify="right")
                table.add_column("Last Updated", style="dim")

                for ent in indexed_entities:
                    table.add_row(
                        ent["entity"],
                        str(ent["indexed"]),
                        str(ent.get("pending", 0)),
                        ent.get("last_updated", "—"),
                    )

                console.print(table)
            else:
                console.print("[yellow]No entities indexed yet[/yellow]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@embeddings_app.command("reindex")
def embeddings_reindex(
    ctx: typer.Context,
    entity: Annotated[
        str | None, typer.Argument(help="Entity to reindex (omit for all)")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Force reindex all records")] = False,
) -> None:
    """Reindex embeddings for an entity or all entities.

    Examples:
        kameleondb embeddings reindex
        kameleondb embeddings reindex Contact
        kameleondb embeddings reindex Contact --force
    """
    try:
        cli_ctx: CLIContext = ctx.obj
        db = cli_ctx.get_db()

        if not db._embeddings_enabled:
            console.print("[red]Error:[/red] Embeddings not enabled")
            raise typer.Exit(1)

        target = entity or "all entities"
        console.print(f"[cyan]Reindexing:[/cyan] {target}{'[dim] (forced)[/dim]' if force else ''}")

        # TODO: Implement force flag in reindex_embeddings()
        result = db.reindex_embeddings(entity_name=entity)

        console.print(f"[green]✓[/green] Reindexed {result.get('indexed', 0)} records")
        if result.get("skipped"):
            console.print(f"  [dim]Skipped {result['skipped']} already indexed[/dim]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# Export for main CLI
__all__ = ["search_command", "embeddings_app"]
