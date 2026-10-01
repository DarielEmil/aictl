"""Comprobaciones de acceso: que el vault se pueda leer y los destinos se puedan escribir.

Las usan `init`, `update` y `doctor` para detectar problemas antes del sync
(permisos de macOS en Google Drive/iCloud, carpetas vacías sin sincronizar...).
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from aictl.config import Config
from aictl.mapping import Mapping
from aictl.sources import ObsidianSource, SourceError
from aictl.sources.obsidian import PERMISSION_HINT, _subfolders

SYNC_HINT = (
    "si está en Google Drive/iCloud puede que aún no se haya sincronizado en este equipo "
    "(en Finder: clic derecho → Disponible sin conexión)"
)


@dataclass
class Check:
    level: str 
    message: str


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def ok(self, message: str) -> None:
        self.checks.append(Check("ok", message))

    def warn(self, message: str) -> None:
        self.checks.append(Check("warn", message))

    def error(self, message: str) -> None:
        self.checks.append(Check("error", message))

    def extend(self, other: Report) -> Report:
        self.checks += other.checks
        return self

    @property
    def has_errors(self) -> bool:
        return any(c.level == "error" for c in self.checks)


def readable_dir(path: Path) -> str | None:
    """None si la carpeta existe y se puede listar; si no, el motivo."""
    if not path.exists():
        return f"no existe {path}"
    if not path.is_dir():
        return f"{path} no es una carpeta"
    try:
        with os.scandir(path) as entries:
            next(entries, None)
    except PermissionError:
        return f"sin permiso para leer {path}. {PERMISSION_HINT}"
    except OSError as exc:
        return f"no se puede leer {path}: {exc.strerror}"
    return None


def check_source(cfg: Config) -> Report:
    report = Report()
    src = cfg.source
    if problem := readable_dir(src.vault):
        report.error(f"vault: {problem}")
        return report
    report.ok(f"vault legible: {src.vault}")

    usable = 0
    for label, path in (("agents", src.agents_path), ("skills", src.skills_path)):
        if not path.exists():
            report.warn(f"{label}: no existe {path}")
            continue
        if problem := readable_dir(path):
            report.error(f"{label}: {problem}")
            continue
        usable += 1
        if not _subfolders(path):
            report.warn(f"{label}: la carpeta {path} está vacía; {SYNC_HINT}")
        else:
            report.ok(f"{label} legible: {path}")
    if report.has_errors:
        return report
    if usable == 0:
        report.error("no existe ninguna de las carpetas de agents ni de skills")
        return report

    _warn_skipped_folders(report, src.agents_path, src.skills_path)

    source = ObsidianSource(src.vault, src.agents_path, src.skills_path)
    try:
        items = source.items()
    except SourceError as exc:
        report.error(str(exc))
        return report

    unreadable = []
    for item in items:
        for file in item.files():
            try:
                file.read_bytes()
            except OSError as exc:
                unreadable.append(f"{file} ({exc.strerror})")
    if unreadable:
        report.error("no se pudieron leer: " + "; ".join(unreadable))

    agents = sum(1 for i in items if i.kind == "agent")
    skills = len(items) - agents
    if not items:
        report.warn(f"no se encontró ningún agent ni skill para sincronizar; {SYNC_HINT}")
    elif not unreadable:
        report.ok(f"{agents} agents y {skills} skills encontrados y legibles")
    return report


def _warn_skipped_folders(report: Report, agents_dir: Path, skills_dir: Path) -> None:
    """Carpetas que se ignorarán: suele indicar estructura incorrecta o sync incompleto."""
    no_md = [f.name for f in _subfolders(agents_dir) if not any(f.glob("*.md"))]
    if no_md:
        report.warn(f"agents sin ningún .md (se ignoran): {', '.join(no_md)}")
    no_skill = [f.name for f in _subfolders(skills_dir) if not (f / "SKILL.md").is_file()]
    if no_skill:
        report.warn(f"skills sin SKILL.md (se ignoran): {', '.join(no_skill)}")


def check_targets(maps: Mapping, names: list[str]) -> Report:
    """Prueba real de escritura en la carpeta de cada AI (o su primer padre existente)."""
    report = Report()
    for name in names:
        if name not in maps.targets:
            report.error(f"{name}: no está definida en el mapeo ({maps.source})")
            continue
        root = maps.targets[name].root
        if root.exists() and not root.is_dir():
            report.error(f"{name}: {root} existe pero no es una carpeta")
            continue
        base = next((p for p in (root, *root.parents) if p.exists()), None)
        try:
            with tempfile.TemporaryFile(dir=base, prefix=".aictl-check-"):
                pass
        except OSError as exc:
            report.error(f"{name}: no se puede escribir en {base}: {exc.strerror}")
            continue
        report.ok(f"{name}: se puede escribir en {root}")
    return report
