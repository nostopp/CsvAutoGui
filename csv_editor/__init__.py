"""CSV editor package with a pywebview desktop host."""

__version__ = "0.1.0"

def main(argv: list[str] | None = None) -> int:
    from .app import main as app_main

    return app_main(argv)

__all__ = ["__version__", "main"]
