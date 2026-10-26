"""Web API (FastAPI) and the web UI it serves. Needs the ``web`` extra."""

from skytrace.api.app import create_app

__all__ = ["create_app"]
