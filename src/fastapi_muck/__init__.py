from .views import FastAPIMuckApiView
from .callback import FastAPIMuckCallback
from .extension import FastAPIMuck, install_error_pages

__version__ = "0.4.2"

__all__ = [
    "FastAPIMuck",
    "FastAPIMuckApiView",
    "FastAPIMuckCallback",
    "install_error_pages",
]
