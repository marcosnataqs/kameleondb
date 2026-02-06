"""Output formatting for CLI commands."""

import json
from collections.abc import Callable
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from kameleondb.core.types import EntityInfo
from kameleondb.exceptions import KameleonDBError

console = Console()


class OutputFormatter:
    """Formats output for terminal or JSON mode."""

    def __init__(self, json_mode: bool = False) -> None:
        """Initialize formatter.

        Args:
            json_mode: If True, output JSON instead of Rich formatting
        """
        self.json_mode = json_mode

    def print_table(
        self,
        title: str,
        data: list[dict[str, Any]],
        columns: list[str],
    ) -> None:
        """Print data as Rich table or JSON array.

        Args:
            title: Table title
            data: List of row dictionaries
            columns: Column names to display
        """
        if self.json_mode:
            print(json.dumps(data, default=str, indent=2))
        else:
            table = Table(title=title, show_header=True, header_style="bold magenta")
            for col in columns:
                table.add_column(col)
            for row in data:
                table.add_row(*[str(row.get(col, "")) for col in columns])
            console.print(table)

    def print_entity_info(self, entity: EntityInfo) -> None:
        """Print entity information with fields and relationships.

        Args:
            entity: Entity information to display
        """
        if self.json_mode:
            # Use model_dump() for Pydantic v2 compatibility
            print(json.dumps(entity.model_dump(), default=str, indent=2))
        else:
            # Entity header
            console.print(f"\n[bold]Entity:[/bold] {entity.name}")
            console.print(f"Storage: {entity.storage_mode}")
            if entity.record_count is not None:
                console.print(f"Records: {entity.record_count:,}")
            if entity.description:
                console.print(f"Description: {entity.description}")
            if entity.created_at:
                console.print(f"Created: {entity.created_at}")

            # Fields table
            if entity.fields:
                console.print(f"\n[bold]Fields ({len(entity.fields)}):[/bold]")
                fields_table = Table(show_header=True, header_style="bold cyan")
                fields_table.add_column("Name")
                fields_table.add_column("Type")
                fields_table.add_column("Required")
                fields_table.add_column("Unique")
                fields_table.add_column("Indexed")

                for field in entity.fields:
                    fields_table.add_row(
                        field.name,
                        field.type,
                        "✓" if field.required else "",
                        "✓" if field.unique else "",
                        "✓" if field.indexed else "",
                    )
                console.print(fields_table)

            # Relationships table
            if entity.relationships:
                console.print(f"\n[bold]Relationships ({len(entity.relationships)}):[/bold]")
                rel_table = Table(show_header=True, header_style="bold cyan")
                rel_table.add_column("Name")
                rel_table.add_column("To Entity")
                rel_table.add_column("Type")

                for rel in entity.relationships:
                    rel_table.add_row(
                        rel.name,
                        rel.target_entity,
                        rel.relationship_type,
                    )
                console.print(rel_table)

    def print_success(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Print success message.

        Args:
            message: Success message
            details: Optional details to display
        """
        if self.json_mode:
            output = {"success": True, "message": message}
            if details:
                output.update(details)
            print(json.dumps(output, default=str, indent=2))
        else:
            console.print(f"✓ {message}", style="green")
            if details:
                for key, value in details.items():
                    console.print(f"  {key}: {value}", style="dim")

    def print_error(self, error: Exception) -> None:
        """Print error message.

        Args:
            error: Exception to display
        """
        if self.json_mode:
            if isinstance(error, KameleonDBError):
                print(json.dumps(error.to_dict(), indent=2))
            else:
                print(json.dumps({"error": str(error)}, indent=2))
        else:
            error_text = str(error)
            # For KameleonDBError, include context if available
            if isinstance(error, KameleonDBError) and error.context:
                context_str = "\n".join(f"{k}: {v}" for k, v in error.context.items())
                error_text = f"{error_text}\n\n{context_str}"

            panel = Panel(
                error_text,
                title="[red]Error[/red]",
                border_style="red",
            )
            console.print(panel)

    def print_data(self, data: Any) -> None:
        """Print generic data (dict, list, etc.).

        Args:
            data: Data to print
        """
        if self.json_mode:
            print(json.dumps(data, default=str, indent=2))
        else:
            # Pretty print with Rich
            import pprint

            pprint.pprint(data)


class ProgressBarWrapper:
    """Wrapper for Rich Progress with migration callback support."""

    def __init__(self, json_mode: bool = False) -> None:
        """Initialize progress wrapper.

        Args:
            json_mode: If True, print JSON progress updates
        """
        self.json_mode = json_mode
        self.progress: Progress | None = None
        self.task_id: TaskID | None = None

    def __enter__(self) -> "ProgressBarWrapper":
        """Enter context manager."""
        if not self.json_mode:
            self.progress = Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                console=console,
            )
            self.progress.__enter__()
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context manager."""
        if self.progress is not None:
            self.progress.__exit__(*args)

    def create_task(self, description: str, total: int) -> TaskID | None:
        """Create progress task.

        Args:
            description: Task description
            total: Total units of work

        Returns:
            Task ID or None in JSON mode
        """
        if self.progress is not None:
            self.task_id = self.progress.add_task(description, total=total)
            return self.task_id
        return None

    def update(self, advance: int = 1) -> None:
        """Update progress.

        Args:
            advance: Number of units completed
        """
        if self.progress is not None and self.task_id is not None:
            self.progress.update(self.task_id, advance=advance)

    def create_callback(self, entity_name: str) -> Callable[[Any], None]:
        """Create migration progress callback.

        Args:
            entity_name: Entity being migrated

        Returns:
            Callback function for migration progress
        """

        def callback(progress: Any) -> None:
            """Migration progress callback.

            Args:
                progress: MigrationProgress object
            """
            if self.json_mode:
                # Print JSON progress update
                console.print(
                    json.dumps(
                        {
                            "entity": progress.entity_name,
                            "direction": progress.direction,
                            "migrated": progress.migrated_records,
                            "total": progress.total_records,
                            "percentage": progress.percentage,
                        }
                    )
                )
            elif self.progress is not None:
                # Update progress bar
                if self.task_id is None:
                    self.task_id = self.progress.add_task(
                        f"Migrating {entity_name}",
                        total=progress.total_records,
                    )
                self.progress.update(self.task_id, completed=progress.migrated_records)

        return callback
