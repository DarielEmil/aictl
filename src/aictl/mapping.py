"""YAML de mapeo: qué copiar, a dónde y con qué transformaciones, por cada AI."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml

from aictl import transforms
from aictl.config import Config, config_dir


class MappingError(Exception):
    pass


@dataclass
class Rule:
    kind: str 
    dest: str 
    transform: list[str] = field(default_factory=list)

    @property
    def is_dir(self) -> bool:
        return self.dest.endswith("/")

    @property
    def is_concat(self) -> bool:
        return "concat" in self.transform


@dataclass
class Target:
    name: str
    root: Path
    rules: list[Rule]

    def describe(self) -> list[str]:
        return [f"{self.root / r.dest}  ({r.kind}s)" for r in self.rules]


@dataclass
class Mapping:
    targets: dict[str, Target]
    source: str 

    def get(self, name: str) -> Target:
        if name not in self.targets:
            raise MappingError(f"La AI '{name}' no está definida en el mapeo ({self.source})")
        return self.targets[name]


def default_text() -> str:
    return resources.files("aictl.data").joinpath("targets.yaml").read_text(encoding="utf-8")


def user_mapping_path() -> Path:
    return config_dir() / "targets.yaml"


def resolve_path(cfg: Config | None) -> Path | None:
    """Prioridad: mapping_file de la config > ~/.config/aictl/targets.yaml > el del paquete."""
    if cfg and cfg.mapping_file:
        path = Path(cfg.mapping_file).expanduser()
        if not path.is_file():
            raise MappingError(f"mapping_file no existe: {path}")
        return path
    user = user_mapping_path()
    return user if user.is_file() else None


def load(cfg: Config | None = None) -> Mapping:
    path = resolve_path(cfg)
    text = path.read_text(encoding="utf-8") if path else default_text()
    return parse(text, str(path) if path else "default")


def parse(text: str, source: str = "<string>") -> Mapping:
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise MappingError(f"YAML inválido en {source}: {exc}") from exc
    raw_targets = data.get("targets")
    if not isinstance(raw_targets, dict) or not raw_targets:
        raise MappingError(f"{source}: falta la sección 'targets'")

    targets = {}
    for name, raw in raw_targets.items():
        if not isinstance(raw, dict) or "root" not in raw:
            raise MappingError(f"{source}: el target '{name}' necesita 'root'")
        rules = [_parse_rule(name, r, source) for r in raw.get("rules") or []]
        targets[name] = Target(name, Path(raw["root"]).expanduser(), rules)
    return Mapping(targets, source)


def _parse_rule(target: str, raw: dict, source: str) -> Rule:
    where = f"{source} [{target}]"
    if not isinstance(raw, dict):
        raise MappingError(f"{where}: cada regla debe ser un objeto")
    kind = raw.get("kind")
    dest = raw.get("dest")
    names = raw.get("transform") or []
    if isinstance(names, str):
        names = [names]
    if kind not in ("agent", "skill"):
        raise MappingError(f"{where}: kind debe ser 'agent' o 'skill', no {kind!r}")
    if not dest or not isinstance(dest, str):
        raise MappingError(f"{where}: falta 'dest'")
    if dest.startswith("/") or ".." in Path(dest).parts:
        raise MappingError(f"{where}: dest debe ser relativo a root y sin '..': {dest}")
    unknown = [n for n in names if n not in transforms.TRANSFORMS and n not in transforms.SPECIAL]
    if unknown:
        raise MappingError(f"{where}: transform desconocido {unknown}")

    rule = Rule(kind, dest, list(names))
    if rule.is_dir and kind != "skill":
        raise MappingError(f"{where}: solo las skills pueden copiarse a una carpeta ({dest})")
    if rule.is_concat and (rule.is_dir or "{name}" in dest):
        raise MappingError(f"{where}: con 'concat' el dest debe ser un único archivo ({dest})")
    if not rule.is_concat and "{name}" not in dest:
        raise MappingError(f"{where}: dest debe contener {{name}} o usar 'concat' ({dest})")
    return rule
