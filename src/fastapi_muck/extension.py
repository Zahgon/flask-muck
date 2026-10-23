import json
from typing import Any, Optional

from apispec import APISpec
from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from fastapi_muck import FastAPIMuckApiView
from fastapi_muck.apidocs import (
    DEFAULT_STATIC_URL_PATH,
    render_apidocs_ui,
    static_files,
)
from fastapi_muck.app_context import current_app
from fastapi_muck.commands import muck_cli
from fastapi_muck.http_errors import (
    HTMLDebugMiddleware,
    WerkzeugRoutingMiddleware,
    http_exception_handler,
    internal_server_error_handler,
)
from fastapi_muck.responses import MuckJSONResponse, MuckResponse
from fastapi_muck.types import JsonDict
from fastapi_muck.utils import register_muck_view

#: Where the API's OpenAPI document is published. The original apidocs UI was
#: served by a Swagger integration that put the document on this fixed url,
#: independent of where the UI itself was mounted.
DEFAULT_APIDOCS_SPEC_URL_PATH = "/apispec_1.json"


def install_error_pages(app: FastAPI) -> None:
    """Makes the app answer errors and slash redirects like the original API.

    FastAPI's default handler renders an HTTP error as a JSON envelope and
    Starlette answers a missing trailing slash with a body-less 307; the
    original API served HTML error pages and a 308. On a debug app, Starlette
    also downgrades its traceback page to plain text for a client that did not
    ask for html, which the original debugger never did. Since a generated
    API's error responses are as much of its contract as its successful ones,
    the original rendering is what the extension installs.
    """
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    # Outside debug mode an unhandled exception is answered with the original 500 page.
    app.add_exception_handler(Exception, internal_server_error_handler)
    app.router.redirect_slashes = False
    app.add_middleware(WerkzeugRoutingMiddleware, router=app.router)
    if app.debug:
        app.add_middleware(HTMLDebugMiddleware)


class FastAPIMuck:
    registered_views: list[type[FastAPIMuckApiView]]
    url_prefix: str
    apidocs_url_path: Optional[str]
    apidocs_spec_url_path: Optional[str]
    _apidocs_template: Optional[JsonDict]
    _spec: APISpec

    def __init__(self, app: Optional[FastAPI] = None) -> None:
        self.apidocs_url_path = None
        self.apidocs_spec_url_path = None
        self._apidocs_template = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app: FastAPI) -> None:
        self.registered_views = []
        app.state.muck = self
        config = app.extra
        api_title = config.setdefault("MUCK_API_TITLE", "REST API")
        openapi_version = "3.0.3"

        self._spec = APISpec(
            title=api_title,
            version=config.setdefault("MUCK_API_VERSION", "1.0.0"),
            openapi_version=openapi_version,
        )
        self.url_prefix = config.setdefault("MUCK_API_URL_PREFIX", "/")
        install_error_pages(app)

        if config.setdefault("MUCK_APIDOCS_ENABLED", True):
            self.apidocs_url_path = config.setdefault(
                "MUCK_APIDOCS_URL_PATH", "/apidocs/"
            )
            ui_config: JsonDict = {
                "openapi": openapi_version,
                "specs_route": self.apidocs_url_path,
            }
            if not config.setdefault("MUCK_APIDOCS_INTERACTIVE", False):
                # A non-interactive UI is one with no method the "Try it out"
                # button will submit.
                ui_config["ui_params"] = {"supportedSubmitMethods": []}
            self._register_apidocs(app, ui_config)
            # The docs UI took its template from the spec as soon as it was set up, and again after every
            # registration. ``APISpec.to_dict`` keeps what it renders, so this also fixes the key order of every
            # later rendering of the spec, and is kept for that reason.
            self._apidocs_template = self._spec.to_dict()

        app.state.muck_cli = muck_cli

    def _register_apidocs(self, app: FastAPI, ui_config: JsonDict) -> None:
        self.apidocs_spec_url_path = app.extra.setdefault(
            "MUCK_APIDOCS_SPEC_URL_PATH", DEFAULT_APIDOCS_SPEC_URL_PATH
        )
        spec_url = str(self.apidocs_spec_url_path)
        # The UI is a template plus a static asset bundle, both served by this
        # package, so the page has no third-party origin to reach out to.
        static_url_path = str(
            app.extra.setdefault(
                "MUCK_APIDOCS_STATIC_URL_PATH", DEFAULT_STATIC_URL_PATH
            )
        )

        def openapi_document() -> JsonDict:
            return self._spec.to_dict()

        def openapi_json() -> Response:
            # The document is a response body like any other, so it is rendered
            # the way the rest of the API renders its bodies.
            return MuckJSONResponse(self._spec.to_dict(), debug=app.debug)

        def apidocs_ui() -> Response:
            return MuckResponse(
                media_type="text/html",
                content=render_apidocs_ui(
                    spec_url=spec_url,
                    ui_config=ui_config,
                    app_config=app.extra,
                    static_url_path=static_url_path,
                )
            )

        app.mount(static_url_path, static_files(), name="muck_apidocs_static")

        app.add_api_route(
            spec_url, openapi_json, methods=["GET", "HEAD"], include_in_schema=False
        )
        app.add_api_route(
            str(self.apidocs_url_path),
            apidocs_ui,
            methods=["GET", "HEAD"],
            include_in_schema=False,
        )
        # FastAPI caches the document it builds from its own routes; the muck
        # views are registered with ``include_in_schema=False``, so the apispec
        # document is the only complete one and has to replace it.
        app.openapi = openapi_document  # type: ignore[method-assign]

    @property
    def openapi_spec_json(self) -> Optional[str]:
        """Returns a json representation of the OpenAPI spec generated by the FastAPIMuckApiViews registered."""
        if self._spec:
            return json.dumps(self._spec.to_dict(), indent=2)
        return None

    @property
    def openapi_spec_dict(self) -> Optional[JsonDict]:
        """Returns a dict representation of the OpenAPI spec generated by the FastAPIMuckApiViews registered."""
        if self._spec:
            return self._spec.to_dict()
        return None

    def register_muck_views(
        self,
        muck_views: list[type[FastAPIMuckApiView]],
        app: Optional[FastAPI] = None,
    ) -> None:
        api: Any = app or current_app()
        for view in muck_views:
            if view not in self.registered_views:
                register_muck_view(
                    muck_view=view,
                    api=api,
                    api_spec=self._spec,
                    url_prefix=self.url_prefix,
                )
                self.registered_views.append(view)

                # Refresh the docs template.
                if self.apidocs_url_path is not None:
                    self._apidocs_template = self._spec.to_dict()
