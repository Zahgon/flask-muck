from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Iterator, Optional

if TYPE_CHECKING:
    from fastapi import FastAPI

_current_app: ContextVar[Optional["FastAPI"]] = ContextVar(
    "fastapi_muck_current_app", default=None
)


@contextmanager
def app_context(app: "FastAPI") -> Iterator["FastAPI"]:
    """Binds a FastAPI app to the current context.

    FastAPI has no equivalent of an application context, but the CLI needs a way to find the app it should operate on.
    Push one around any code that needs ``current_app``.
    """
    token = _current_app.set(app)
    try:
        yield app
    finally:
        _current_app.reset(token)


def current_app() -> Optional["FastAPI"]:
    """Returns the FastAPI app bound to the current context, if there is one."""
    return _current_app.get()
