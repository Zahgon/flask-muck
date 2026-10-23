import json

import typer
from rich import print_json

from fastapi_muck.app_context import current_app

muck_cli = typer.Typer(name="muck")


@muck_cli.command()
def openapi_spec() -> None:
    """Print OpenAPI spec JSON for this app's API."""
    app = current_app()
    if app is None or (muck := getattr(app.state, "muck", None)) is None:
        print("No FastAPI-Muck extension initialized in this app")
        return
    print_json(json.dumps(muck.spec.to_dict(), indent=2))
