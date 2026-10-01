"""Fuente Obsidian: lee agents y skills desde carpetas de un vault local."""

from __future__ import annotations

from pathlib import Path

from aictl.frontmatter import parse
from aictl.sources.base import Item, Source

IGNORED_DIRS = {".obsidian", ".trash", ".git"}
PERMISSION_HINT = (
    "En macOS, las carpetas de Google Drive/iCloud requieren dar acceso a tu terminal en "
    "Ajustes del Sistema → Privacidad y seguridad → Archivos y carpetas (o Acceso total al disco)."
)


class SourceError(Exception):
    pass


class ObsidianSource(Source):
    def __init__(self, vault: Path, agents_dir: Path, skills_dir: Path):
        self.vault = vault
        self.agents_dir = agents_dir
        self.skills_dir = skills_dir

    def validate(self) -> list[str]:
        problems = []
        if not self.vault.is_dir():
            problems.append(f"El vault no existe: {self.vault}")
            return problems
        if not self.agents_dir.is_dir() and not self.skills_dir.is_dir():
            problems.append(
                f"No existe ninguna de las carpetas de agents ({self.agents_dir}) "
                f"ni de skills ({self.skills_dir})"
            )
        return problems

    def items(self) -> list[Item]:
        problems = self.validate()
        if problems:
            raise SourceError("; ".join(problems))
        try:
            items = self._agents() + self._skills()
        except PermissionError as exc:
            raise SourceError(f"Sin permiso para leer {exc.filename}. {PERMISSION_HINT}") from exc
        except OSError as exc:
            raise SourceError(f"No se pudo leer {exc.filename}: {exc.strerror}") from exc
        seen: dict[tuple[str, str], Path] = {}
        for item in items:
            key = (item.kind, item.name)
            if key in seen:
                raise SourceError(
                    f"Nombre de {item.kind} duplicado '{item.name}': {seen[key]} y {item.path}"
                )
            seen[key] = item.path
        return items

    def _agents(self) -> list[Item]:
        """Cada subcarpeta de agents/ es un agent y contiene un único .md."""
        items = []
        for folder in _subfolders(self.agents_dir):
            md_files = sorted(
                p for p in folder.glob("*.md") if p.is_file() and not p.name.startswith(".")
            )
            if not md_files:
                continue
            if len(md_files) > 1:
                names = ", ".join(p.name for p in md_files)
                raise SourceError(
                    f"El agent '{folder.name}' debe tener un único .md y tiene varios: {names}"
                )
            path = md_files[0]
            text = path.read_text(encoding="utf-8")
            meta, _ = parse(text)
            if meta.get("aictl") is False:
                continue
            name = str(meta.get("name") or folder.name)
            items.append(Item("agent", name, path, meta, text))
        return items

    def _skills(self) -> list[Item]:
        """Cada subcarpeta de skills/ con un SKILL.md es una skill (se copia la carpeta entera)."""
        items = []
        for folder in _subfolders(self.skills_dir):
            skill_md = folder / "SKILL.md"
            if not skill_md.is_file():
                continue
            text = skill_md.read_text(encoding="utf-8")
            meta, _ = parse(text)
            if meta.get("aictl") is False:
                continue
            name = str(meta.get("name") or folder.name)
            items.append(Item("skill", name, folder, meta, text))
        return items


def _subfolders(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        p
        for p in root.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name not in IGNORED_DIRS
    )


def list_subdirs(root: Path) -> list[str]:
    """Subcarpetas del vault (relativas), útil para los prompts de init/update."""
    if not root.is_dir():
        return []
    result = []
    try:
        paths = sorted(root.rglob("*"))
    except OSError:
        return []
    for path in paths:
        rel = path.relative_to(root)
        if not path.is_dir() or any(p.startswith(".") or p in IGNORED_DIRS for p in rel.parts):
            continue
        if len(rel.parts) <= 3:
            result.append(rel.as_posix())
    return result
