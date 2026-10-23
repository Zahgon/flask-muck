"""The HTML error pages and redirects the original API served.

The wire contract of a generated API includes what it answers when a request
goes wrong, and the Flask original handed every HTTP error to Werkzeug, which
rendered a small HTML document and sent it as ``text/html; charset=utf-8``.
FastAPI answers with a JSON ``{"detail": ...}`` envelope instead, and Starlette
answers a missing trailing slash with a body-less 307 rather than Werkzeug's
308 page.

Everything needed to reproduce the original responses lives here;
:class:`~fastapi_muck.extension.FastAPIMuck` installs it on the app.
"""

from __future__ import annotations

import re
from http import HTTPStatus
from typing import Optional
from urllib.parse import quote, urlsplit, urlunsplit

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.errors import ServerErrorMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Match, Router
from starlette.types import ASGIApp, Receive, Scope, Send

from fastapi_muck.responses import MuckResponse

#: ``status code -> (status name, default description)``, transcribed from the
#: exception classes the original stack rendered its error pages from. The
#: description is what an error page shows when the code that raised the error
#: did not supply one of its own.
STATUS_PAGES: dict[int, tuple[str, str]] = {
    400: (
        "Bad Request",
        "The browser (or proxy) sent a request that this server could not understand.",
    ),
    401: (
        "Unauthorized",
        "The server could not verify that you are authorized to access the URL "
        "requested. You either supplied the wrong credentials (e.g. a bad "
        "password), or your browser doesn't understand how to supply the "
        "credentials required.",
    ),
    403: (
        "Forbidden",
        "You don't have the permission to access the requested resource. It is "
        "either read-protected or not readable by the server.",
    ),
    404: (
        "Not Found",
        "The requested URL was not found on the server. If you entered the URL "
        "manually please check your spelling and try again.",
    ),
    405: ("Method Not Allowed", "The method is not allowed for the requested URL."),
    406: (
        "Not Acceptable",
        "The resource identified by the request is only capable of generating "
        "response entities which have content characteristics not acceptable "
        "according to the accept headers sent in the request.",
    ),
    408: (
        "Request Timeout",
        "The server closed the network connection because the browser didn't "
        "finish the request within the specified time.",
    ),
    409: (
        "Conflict",
        "A conflict happened while processing the request. The resource might "
        "have been modified while the request was being processed.",
    ),
    410: (
        "Gone",
        "The requested URL is no longer available on this server and there is no "
        "forwarding address. If you followed a link from a foreign page, please "
        "contact the author of this page.",
    ),
    411: (
        "Length Required",
        "A request with this method requires a valid <code>Content-Length</code> header.",
    ),
    412: (
        "Precondition Failed",
        "The precondition on the request for the URL failed positive evaluation.",
    ),
    413: (
        "Request Entity Too Large",
        "The data value transmitted exceeds the capacity limit.",
    ),
    414: (
        "Request URI Too Long",
        "The length of the requested URL exceeds the capacity limit for this "
        "server. The request cannot be processed.",
    ),
    415: (
        "Unsupported Media Type",
        "The server does not support the media type transmitted in the request.",
    ),
    416: (
        "Requested Range Not Satisfiable",
        "The server cannot provide the requested range.",
    ),
    417: (
        "Expectation Failed",
        "The server could not meet the requirements of the Expect header",
    ),
    418: ("I'm a teapot", "This server is a teapot, not a coffee machine"),
    421: ("Misdirected Request", "The server is not able to produce a response."),
    422: (
        "Unprocessable Entity",
        "The request was well-formed but was unable to be followed due to "
        "semantic errors.",
    ),
    423: ("Locked", "The resource that is being accessed is locked."),
    424: (
        "Failed Dependency",
        "The method could not be performed on the resource because the requested "
        "action depended on another action and that action failed.",
    ),
    428: (
        "Precondition Required",
        'This request is required to be conditional; try using "If-Match" or '
        '"If-Unmodified-Since".',
    ),
    429: (
        "Too Many Requests",
        "This user has exceeded an allotted request count. Try again later.",
    ),
    431: (
        "Request Header Fields Too Large",
        "One or more header fields exceeds the maximum size.",
    ),
    451: ("Unavailable For Legal Reasons", "Unavailable for legal reasons."),
    500: (
        "Internal Server Error",
        "The server encountered an internal error and was unable to complete "
        "your request. Either the server is overloaded or there is an error in "
        "the application.",
    ),
    501: (
        "Not Implemented",
        "The server does not support the action requested by the browser.",
    ),
    502: (
        "Bad Gateway",
        "The proxy server received an invalid response from an upstream server.",
    ),
    503: (
        "Service Unavailable",
        "The server is temporarily unable to service your request due to "
        "maintenance downtime or capacity problems. Please try again later.",
    ),
    504: ("Gateway Timeout", "The connection to an upstream server timed out."),
    505: (
        "HTTP Version Not Supported",
        "The server does not support the HTTP protocol version used in the request.",
    ),
}

#: The status the original router used when it appended a missing trailing slash.
SLASH_REDIRECT_STATUS_CODE = 308


def escape(value: str) -> str:
    """HTML-escapes a string the way the original error pages were escaped."""
    return (
        value.replace("&", "&amp;")
        .replace(">", "&gt;")
        .replace("<", "&lt;")
        .replace("'", "&#39;")
        .replace('"', "&#34;")
    )


def _status_name(status_code: int) -> str:
    if status_code in STATUS_PAGES:
        return STATUS_PAGES[status_code][0]
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Unknown Error"


def render_error_page(status_code: int, description: str) -> str:
    """Renders the error document for a status code and description."""
    name = _status_name(status_code)
    body = escape(description).replace("\n", "<br>")
    return (
        "<!doctype html>\n"
        "<html lang=en>\n"
        f"<title>{status_code} {escape(name)}</title>\n"
        f"<h1>{escape(name)}</h1>\n"
        f"<p>{body}</p>\n"
    )


def error_response(
    status_code: int,
    description: str,
    headers: Optional[dict[str, str]] = None,
) -> Response:
    """Builds the ``text/html`` error response for a status code."""
    return MuckResponse(
        content=render_error_page(status_code, description),
        status_code=status_code,
        headers=headers,
        media_type="text/html",
    )


def redirect_response(
    location: str, status_code: int = SLASH_REDIRECT_STATUS_CODE
) -> Response:
    """Builds the little "Redirecting..." page the original router replied with.

    The page shows the target as it was built; the ``Location`` header, which follows the content length, carries
    it converted to a URI (characters a URI cannot hold percent-encoded).
    """
    html_location = escape(location)
    response = MuckResponse(
        content=(
            "<!doctype html>\n"
            "<html lang=en>\n"
            "<title>Redirecting...</title>\n"
            "<h1>Redirecting...</h1>\n"
            "<p>You should be redirected automatically to the target URL: "
            f'<a href="{html_location}">{html_location}</a>. '
            "If not, click the link.\n"
        ),
        status_code=status_code,
        media_type="text/html",
    )
    response.raw_headers.append((b"location", _to_uri(location).encode("latin-1")))
    return response


def _to_uri(location: str) -> str:
    """Percent-encodes what a URI cannot carry, leaving existing escapes and reserved characters alone."""
    parts = urlsplit(location)
    path = quote(parts.path, safe="%!$&'()*+,/:;=@")
    query = quote(parts.query, safe="%!$&'()*+,/:;=?@")
    return urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def options_response(allowed: str) -> Response:
    """The automatic answer to ``OPTIONS``: an empty html document naming the url's methods."""
    return MuckResponse(
        content=b"", status_code=200, headers={"Allow": allowed}, media_type="text/html"
    )


def description_for(exc: StarletteHTTPException) -> str:
    """Returns the description an error page should show for an exception.

    ``HTTPException`` always carries a ``detail``: Starlette fills it with the
    status phrase when the raiser gave none, and query validation puts a mapping
    of field errors there. Neither is a human description, so in both cases the
    status code's standard description is used - which is what the original
    pages showed for exactly the same two situations.
    """
    default_description = STATUS_PAGES.get(exc.status_code, ("", ""))[1]
    detail = exc.detail
    if not isinstance(detail, str):
        return default_description
    if detail in (_status_name(exc.status_code), _phrase(exc.status_code)):
        return default_description
    return detail


def _phrase(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return ""


def allowed_methods_for(request: Request) -> Optional[str]:
    """Returns the ``Allow`` header value for the url a request was made to.

    Starlette fills ``Allow`` from the single route it happened to match first,
    which under-reports a path served by more than one route: ``DELETE`` on a
    collection reported ``POST`` even though the same url also serves ``GET``.
    Every method registered for the path is collected here instead, plus the
    ``HEAD`` and ``OPTIONS`` the server answers automatically.

    The methods are joined in a fixed order. The original router iterated a set
    and so shuffled the value from one process to the next; a stable order is
    the one thing a client can actually rely on.
    """
    router = request.scope.get("router")
    if router is None:
        return None
    methods: set[str] = set()
    for route in router.routes:
        route_methods = getattr(route, "methods", None)
        if not route_methods:
            continue
        match, _ = route.matches(request.scope)
        if match is Match.NONE:
            continue
        methods.update(route_methods)
    if not methods:
        return None
    if "GET" in methods:
        methods.add("HEAD")
    methods.add("OPTIONS")
    return ", ".join(sorted(methods, reverse=True))


async def http_exception_handler(request: Request, exc: Exception) -> Response:
    """Renders an ``HTTPException`` as the error page the original API served."""
    assert isinstance(exc, StarletteHTTPException)
    headers = {k: v for k, v in (exc.headers or {}).items()}
    if any(key.lower() == "allow" for key in headers):
        headers = {k: v for k, v in headers.items() if k.lower() != "allow"}
        allowed = allowed_methods_for(request)
        if allowed:
            headers["Allow"] = allowed
    return error_response(exc.status_code, description_for(exc), headers or None)


async def internal_server_error_handler(request: Request, exc: Exception) -> Response:
    """Renders an unhandled exception as the original 500 page (the app is not in debug mode)."""
    return error_response(500, STATUS_PAGES[500][1])


def _route_path(scope: Scope) -> str:
    path: str = scope["path"]
    root_path: str = scope.get("root_path", "")
    if not root_path or not path.startswith(root_path):
        return path
    if path == root_path:
        return ""
    if path[len(root_path) :].startswith("/"):
        return path[len(root_path) :]
    return path


#: Characters the original router left unquoted in the path of a redirect target.
REDIRECT_PATH_SAFE = "!$&'()*+,/:;=@"

#: The original router merged runs of slashes two at a time.
_DOUBLE_SLASH = re.compile("/{2,}?")


class WerkzeugRoutingMiddleware:
    """Resolves a request's url the way the original router did before any view runs.

    Starlette's own ``redirect_slashes`` answers a body-less 307 and redirects in both directions, has no idea of
    merging slashes, and leaves ``OPTIONS`` to the routes. The original router:

    * ignored extra leading slashes;
    * matched a route only when it also accepts the request method (``GET`` routes accept ``HEAD``, every route
      accepts ``OPTIONS``);
    * redirected with a 308 page to the url with a trailing slash when only that one matches for the method, and
      to the url with doubled slashes merged when only that one matches;
    * answered ``OPTIONS`` itself, without running the view, naming every method the url serves;
    * otherwise answered 405 with an ``Allow`` header when the url exists for other methods, and 404 when it does
      not exist at all.

    Installing this middleware therefore goes with turning ``Router.redirect_slashes`` off.
    """

    def __init__(self, app: ASGIApp, router: Router) -> None:
        self.app = app
        self.router = router

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        route_path = _route_path(scope)
        prefix = scope["path"][: len(scope["path"]) - len(route_path)]
        path = "/" + route_path.lstrip("/")
        method = scope["method"]
        scope = dict(scope, path=prefix + path)

        def at(candidate: str) -> Scope:
            return dict(scope, path=prefix + candidate)

        if self._serves(at(path), method):
            if method == "OPTIONS":
                response = options_response(self._allow(at(path)))
                await response(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return
        target = None
        if self._serves(at(path + "/"), method):
            target = path + "/"
        else:
            merged = _DOUBLE_SLASH.sub("/", path)
            if merged != path:
                if self._serves(at(merged), method):
                    target = merged
                elif self._serves(at(merged + "/"), method):
                    target = merged + "/"
        if target is not None:
            response = redirect_response(self._location(scope, prefix + target))
            await response(scope, receive, send)
            return
        allowed = self._methods(at(path))
        merged = _DOUBLE_SLASH.sub("/", path)
        if merged != path:
            allowed |= self._methods(at(merged))
        if allowed:
            response = error_response(
                405, STATUS_PAGES[405][1], {"Allow": _join_methods(allowed)}
            )
        else:
            response = error_response(404, STATUS_PAGES[404][1])
        await response(scope, receive, send)

    def _methods(self, scope: Scope) -> set[str]:
        """Every method some route serves at this url (empty when no route matches the url)."""
        methods: set[str] = set()
        for route in self.router.routes:
            match, _ = route.matches(scope)
            if match is Match.NONE:
                continue
            route_methods = getattr(route, "methods", None)
            methods.update(route_methods or {"GET", "HEAD"})
        return methods

    def _serves(self, scope: Scope, method: str) -> bool:
        methods = self._methods(scope)
        if not methods:
            return False
        return method == "OPTIONS" or method in methods

    def _allow(self, scope: Scope) -> str:
        return _join_methods(self._methods(scope))

    @staticmethod
    def _location(scope: Scope, path: str) -> str:
        host = "localhost"
        for key, value in scope.get("headers", []):
            if key == b"host":
                host = value.decode("latin-1")
                break
        else:
            server = scope.get("server")
            if server:
                host = server[0] if server[1] in (80, 443, None) else f"{server[0]}:{server[1]}"
        location = f"{scope.get('scheme', 'http')}://{host}{quote(path, safe=REDIRECT_PATH_SAFE)}"
        query = scope.get("query_string", b"")
        if query:
            location = f"{location}?{query.decode('latin-1')}"
        return location


def _join_methods(methods: set[str]) -> str:
    methods = set(methods)
    if "GET" in methods:
        methods.add("HEAD")
    methods.add("OPTIONS")
    return ", ".join(sorted(methods, reverse=True))


class HTMLDebugMiddleware(ServerErrorMiddleware):
    """Renders an unhandled exception as an HTML debug page for every client.

    Starlette's debug renderer content-negotiates: it serves its HTML traceback
    page only to a request whose ``Accept`` header mentions ``text/html`` and a
    ``text/plain`` traceback to everything else. The original debugger did not
    negotiate - an unhandled exception came back as ``text/html; charset=utf-8``
    whatever the client asked for, so this drops the negotiation and always
    renders the page.

    It sits inside the debug middleware the framework installs of its own
    accord; both re-raise once the response is on the wire, so the exception
    still reaches the server log exactly as before.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app, debug=True)

    def debug_response(self, request: Request, exc: Exception) -> Response:
        return HTMLResponse(self.generate_html(exc), status_code=500)
