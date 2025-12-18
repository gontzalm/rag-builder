from rich.console import Console
from rich.theme import Theme


def get_console() -> Console:
    return Console(
        theme=Theme(
            {
                "info": "blue",
                "warning": "yellow",
                "success": "bold green",
                "error": "bold red",
                "table": "white",
                "table.header": "bold blue",
                "data": "white",
                "metric": "magenta",
            }
        )
    )
