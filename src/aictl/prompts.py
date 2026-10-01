"""Preguntas interactivas (questionary) usadas por init y update."""

from __future__ import annotations

from pathlib import Path

import questionary
import typer

from aictl import ALL_TARGETS
from aictl.checks import readable_dir
from aictl.sources.obsidian import list_subdirs


def _ask(question: questionary.Question):
    answer = question.ask()
    if answer is None: 
        raise typer.Abort()
    return answer


def vault(default: str = "") -> str:
    def validate(value: str) -> bool | str:
        problem = readable_dir(Path(value).expanduser())
        return f"No se puede usar: {problem}" if problem else True

    answer = _ask(
        questionary.path(
            "Ruta del vault de Obsidian:",
            default=default,
            only_directories=True,
            validate=validate,
        )
    )
    path = Path(answer).expanduser()
    if not (path / ".obsidian").is_dir():
        questionary.print(
            "  Aviso: no se encontró .obsidian/ en esa carpeta; ¿seguro que es un vault?",
            style="fg:yellow",
        )
    return answer


def folder(vault_path: str, label: str, default: str) -> str:
    root = Path(vault_path).expanduser()
    choices = list_subdirs(root)

    def validate(value: str) -> bool | str:
        if not value.strip():
            return "Indica una carpeta"
        problem = readable_dir(root / value)
        return f"No se puede usar: {problem}" if problem else True

    return _ask(
        questionary.autocomplete(
            f"Carpeta de {label} dentro del vault:",
            choices=choices,
            default=default if default in choices else "",
            validate=validate,
            match_middle=True,
        )
    ).strip().strip("/")


def targets(selected: list[str], detected: set[str]) -> list[str]:
    preselect = set(selected) if selected else detected
    choices = [
        questionary.Choice(
            f"{name}{'  (detectado)' if name in detected else ''}",
            value=name,
            checked=name in preselect,
        )
        for name in ALL_TARGETS
    ]
    return _ask(
        questionary.checkbox(
            "¿Qué AIs quieres configurar? (espacio para marcar)",
            choices=choices,
            validate=lambda v: True if v else "Selecciona al menos una AI",
        )
    )


def confirm(message: str, default: bool = True) -> bool:
    return _ask(questionary.confirm(message, default=default))


def select(message: str, choices: list[questionary.Choice]) -> str:
    return _ask(questionary.select(message, choices=choices))
