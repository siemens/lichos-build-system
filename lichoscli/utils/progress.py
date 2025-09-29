"""Simple progress bar utilities for CLI operations."""

from typing import Callable, Optional, TypeVar

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

T = TypeVar("T")


class ProgressUtils:
    """Simple utility class for standardized progress bars."""

    @staticmethod
    def execute_with_progress(
        business_logic: Callable[[], T],
        description: str,
        console: Optional[Console] = None,
        success_message: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> T:
        """Execute a business logic function with automatic progress display.

        This method provides a simple interface for wrapping any business logic
        with a progress spinner. The function will be executed and its result
        returned, while a progress indicator is shown to the user.

        Args:
            business_logic: Function to execute (can be lambda or any callable)
            description: Description to show during execution
            console: Optional Rich console instance
            success_message: Optional message to show on success
            error_message: Optional message to show on error

        Returns:
            The result of the business_logic function

        Raises:
            Any exception raised by the business_logic function
        """
        if console is None:
            console = Console()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description)

            try:
                result = business_logic()

                if success_message:
                    console.print(f"[green]✓[/green] {success_message}")

                return result

            except Exception as e:
                if error_message:
                    console.print(f"[red]✗[/red] {error_message}")
                raise e
