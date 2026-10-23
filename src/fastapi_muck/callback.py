from abc import ABC, abstractmethod
from enum import Enum

from fastapi_muck.types import SqlaModel, JsonDict


class CallbackType(Enum):
    pre = "pre"
    post = "post"


class FastAPIMuckCallback(ABC):
    """The base class for implementing FastAPI Muck callbacks."""

    def __init__(self, resource: SqlaModel, kwargs: JsonDict) -> None:
        self.resource = resource
        self.kwargs = kwargs

    @abstractmethod
    def execute(self) -> None:
        """This method executes the desired callback functionality. It must be overridden in concrete subclasses."""
        ...
