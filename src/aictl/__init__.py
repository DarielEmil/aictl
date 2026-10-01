"""aictl: sincroniza agents y skills desde Obsidian hacia distintas herramientas de IA."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("aictl")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

ALL_TARGETS = ["claude", "opencode", "codex", "antigravity", "cursor", "kiro"]
