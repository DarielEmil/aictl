from aictl.config import Config
from aictl.sources.base import Item, Source
from aictl.sources.obsidian import ObsidianSource, SourceError


def build_source(cfg: Config) -> Source:
    if cfg.source.type == "obsidian":
        return ObsidianSource(cfg.source.vault, cfg.source.agents_path, cfg.source.skills_path)
    raise SourceError(f"Tipo de fuente no soportado: {cfg.source.type}")


__all__ = ["Item", "ObsidianSource", "Source", "SourceError", "build_source"]
