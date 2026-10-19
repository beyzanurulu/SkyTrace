"""SkyTrace: drone flight log analysis."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("skytrace")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0.0.0+unknown"

from skytrace.config import SkyTraceConfig, load_config
from skytrace.parsers.schema import FlightLog

__all__ = ["FlightLog", "SkyTraceConfig", "__version__", "load_config"]
