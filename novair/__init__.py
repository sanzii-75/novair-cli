"""novair — a slick terminal AI agent for any OpenAI-compatible provider."""
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    __version__ = _version("novair-cli")  # single source of truth: pyproject.toml
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0.4.0"

APP_NAME = "novair"
