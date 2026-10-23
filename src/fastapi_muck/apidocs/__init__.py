"""The Swagger UI the API's ``/apidocs/`` page is built from.

The original API mounted its documentation UI with `flasgger
<https://github.com/rochacbruno/flasgger>`_, which is a Flask extension and so
cannot be carried over as a dependency. What that extension actually put on the
wire, though, is a Jinja template and a Swagger UI asset bundle, neither of
which is Flask-specific: ``templates/flasgger`` and ``static`` here are that
template set and that bundle, vendored verbatim from flasgger 0.9.7.1 (MIT) so
the page and every file it pulls are served by this package itself.

Only the UI is vendored. The OpenAPI document behind it is still the one
apispec builds from the registered views, and it is published separately.
"""

import json as json_module
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.staticfiles import StaticFiles

from fastapi_muck.types import JsonDict

#: Release of flasgger the template set and the asset bundle were taken from.
#: It is rendered into the page's footer, which credits the UI's origin.
FLASGGER_UI_VERSION = "0.9.7.1"

#: Url prefix the asset bundle is served under. flasgger used this prefix, and
#: the vendored templates reference the assets through it.
DEFAULT_STATIC_URL_PATH = "/flasgger_static"

#: Title the UI labels itself with. flasgger's own default, which the original
#: API never overrode, so it is what the page carried.
DEFAULT_UI_TITLE = "Flasgger"

HERE = Path(__file__).parent
TEMPLATES_DIR = HERE / "templates"
STATIC_DIR = HERE / "static"

_env: Optional[Environment] = None


def _environment() -> Environment:
    global _env
    if _env is None:
        _env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html"]),
        )
    return _env


def render_apidocs_ui(
    spec_url: str,
    ui_config: JsonDict,
    app_config: Optional[JsonDict] = None,
    title: str = DEFAULT_UI_TITLE,
    static_url_path: str = DEFAULT_STATIC_URL_PATH,
) -> str:
    """Render the Swagger UI page for the document published at ``spec_url``.

    ``ui_config`` is the UI's own configuration -- the mapping the templates
    read ``ui_params``, ``doc_expansion``, ``hide_top_bar`` and the custom
    header/footer text out of. ``app_config`` is the application configuration
    the templates consult for the optional JWT auth hooks.
    """
    static = static_url_path.rstrip("/")
    context: dict[str, Any] = {
        "title": title,
        "specs": [
            {
                "url": spec_url,
                "title": title,
                "name": None,
                "version": "0.0.1",
                "endpoint": "apispec_1",
            }
        ],
        # Only named specs go in the UI's spec picker, and the API publishes a
        # single unnamed document, so the picker stays empty and the UI loads
        # ``specs[0]`` directly.
        "urls": [],
        "flasgger_config": ui_config,
        "config": app_config if app_config is not None else {},
        "json": json_module,
        "flasgger_version": FLASGGER_UI_VERSION,
        "favicon": f"{static}/favicon-32x32.png",
        "swagger_ui_css": f"{static}/swagger-ui.css",
        "swagger_ui_bundle_js": f"{static}/swagger-ui-bundle.js",
        "swagger_ui_standalone_preset_js": f"{static}/swagger-ui-standalone-preset.js",
        "jquery_js": f"{static}/lib/jquery.min.js",
    }
    return _environment().get_template("flasgger/index.html").render(**context)


def static_files() -> StaticFiles:
    """The asset bundle the rendered page loads its css, js and icon from."""
    return StaticFiles(directory=str(STATIC_DIR))
