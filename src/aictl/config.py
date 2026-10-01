"""Configuración del usuario: ~/.config/aictl/config.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIG_VERSION = 1
DEFAULT_AGENTS_DIR = "AI-Config/agents"
DEFAULT_SKILLS_DIR = "AI-Config/skills"


class ConfigError(Exception):
    pass


def config_dir() -> Path:
    """Directorio de configuración de aictl (respeta AICTL_CONFIG_DIR y XDG_CONFIG_HOME)."""
    if env := os.environ.get("AICTL_CONFIG_DIR"):
        return Path(env).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or "~/.config"
    return Path(base).expanduser() / "aictl"


def config_path() -> Path:
    return config_dir() / "config.yaml"


@dataclass
class SourceConfig:
    type: str = "obsidian"
    vault_path: str = ""
    agents_dir: str = DEFAULT_AGENTS_DIR
    skills_dir: str = DEFAULT_SKILLS_DIR

    @property
    def vault(self) -> Path:
        return Path(self.vault_path).expanduser()

    @property
    def agents_path(self) -> Path:
        return self.vault / self.agents_dir

    @property
    def skills_path(self) -> Path:
        return self.vault / self.skills_dir


@dataclass
class Config:
    source: SourceConfig = field(default_factory=SourceConfig)
    targets: list[str] = field(default_factory=list)
    mapping_file: str | None = None

    def to_dict(self) -> dict:
        return {
            "version": CONFIG_VERSION,
            "source": {
                "type": self.source.type,
                "vault_path": self.source.vault_path,
                "agents_dir": self.source.agents_dir,
                "skills_dir": self.source.skills_dir,
            },
            "targets": list(self.targets),
            "mapping_file": self.mapping_file,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Config:
        if not isinstance(data, dict):
            raise ConfigError("config.yaml no tiene un formato válido")
        src = data.get("source") or {}
        return cls(
            source=SourceConfig(
                type=src.get("type", "obsidian"),
                vault_path=src.get("vault_path", ""),
                agents_dir=src.get("agents_dir", DEFAULT_AGENTS_DIR),
                skills_dir=src.get("skills_dir", DEFAULT_SKILLS_DIR),
            ),
            targets=list(data.get("targets") or []),
            mapping_file=data.get("mapping_file"),
        )


def exists() -> bool:
    return config_path().is_file()


def load() -> Config:
    path = config_path()
    if not path.is_file():
        raise ConfigError(f"No existe configuración en {path}. Ejecuta `aictl init` primero.")
    with path.open(encoding="utf-8") as fh:
        return Config.from_dict(yaml.safe_load(fh) or {})


def save(cfg: Config) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg.to_dict(), fh, sort_keys=False, allow_unicode=True)
    return path
