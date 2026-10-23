from __future__ import annotations

import json
from typing import Any, Mapping, Optional

from starlette.responses import Response


class MuckResponse(Response):
    """A response whose headers go out in the order the original Flask APIs emitted them.

    Starlette writes ``content-length`` before ``content-type``. The original stack wrote the content type first,
    then any headers the response was created with, and the content length last. The order is part of what a
    client sees on the wire, so it is reproduced here for every response this package builds.
    """

    def init_headers(self, headers: Optional[Mapping[str, str]] = None) -> None:
        super().init_headers(headers)
        content_type = [h for h in self.raw_headers if h[0] == b"content-type"]
        content_length = [h for h in self.raw_headers if h[0] == b"content-length"]
        others = [
            h
            for h in self.raw_headers
            if h[0] not in (b"content-type", b"content-length")
        ]
        self.raw_headers = content_type + others + content_length


class MuckJSONResponse(MuckResponse):
    """JSON response that renders bodies the way the original Flask APIs did.

    Starlette's ``JSONResponse`` writes compact, insertion-ordered JSON with no
    trailing newline. Flask's provider sorts keys, escapes non-ASCII, indents
    when the app runs in debug mode, and terminates the body with a newline. The
    wire contract of the generated APIs is the product here, so the Flask
    rendering is what gets reproduced.
    """

    media_type = "application/json"

    def __init__(
        self,
        content: Any,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        debug: bool = False,
    ) -> None:
        self.debug = debug
        super().__init__(content, status_code=status_code, headers=headers)

    def render(self, content: Any) -> bytes:
        dump_args: dict[str, Any] = {"sort_keys": True, "ensure_ascii": True}
        if self.debug:
            dump_args["indent"] = 2
        else:
            dump_args["separators"] = (",", ":")
        return f"{json.dumps(content, **dump_args)}\n".encode()


def empty_response(body: str, status_code: int) -> Response:
    """Return a body-less response, matching the original ``("", 204)`` handling.

    Returning a bare string from a view left the framework's default media type
    in place, so even an empty 204 went out labelled ``text/html``. Starlette
    sends no ``Content-Type`` at all unless one is named, so it is named here.
    """
    return MuckResponse(content=body, status_code=status_code, media_type="text/html")
