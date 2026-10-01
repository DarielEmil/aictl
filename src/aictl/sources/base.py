"""Interfaz común para las fuentes de configuración (Obsidian, y en el futuro nube, git...)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Kind = Literal["agent", "skill"]


@dataclass
class Item:
    """Un agent (un archivo .md) o una skill (una carpeta con SKILL.md)."""

    kind: Kind
    name: str
    path: Path  # archivo del agent o carpeta de la skill
    meta: dict = field(default_factory=dict)
    body: str = ""  # contenido completo del .md principal (con frontmatter)

    @property
    def main_file(self) -> Path:
        return self.path / "SKILL.md" if self.kind == "skill" else self.path

    def allowed_for(self, target: str) -> bool:
        """Un item puede limitarse a ciertas AIs con `targets: [...]` en su frontmatter."""
        targets = self.meta.get("targets")
        if not targets:
            return True
        if isinstance(targets, str):
            targets = [t.strip() for t in targets.split(",")]
        return target in targets

    def files(self) -> list[Path]:
        """Archivos que componen el item (para una skill, todos los de su carpeta)."""
        if self.kind == "agent":
            return [self.path]
        return sorted(
            p
            for p in self.path.rglob("*")
            if p.is_file() and not any(part.startswith(".") for part in p.relative_to(self.path).parts)
        )


class Source(ABC):
    @abstractmethod
    def items(self) -> list[Item]: ...
