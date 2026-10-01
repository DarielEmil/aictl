"""Construcción del plan de sync y su ejecución."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from aictl import transforms
from aictl.frontmatter import parse
from aictl.manifest import Manifest, sha256_bytes, sha256_file
from aictl.mapping import Mapping, Rule, Target
from aictl.sources.base import Item

CONCAT_HEADER = (
    "<!-- Generado por aictl desde Obsidian. No editar a mano: "
    "los cambios se sobrescriben con `aictl sync`. -->\n"
)


class SyncError(Exception):
    pass


@dataclass
class Output:
    target: str
    path: Path
    data: bytes
    origin: str 


@dataclass
class Action:
    op: str 
    target: str
    path: Path
    data: bytes | None = None
    reason: str = ""

    @property
    def changes(self) -> bool:
        return self.op in ("create", "update", "delete")



def build_outputs(items: list[Item], mapping: Mapping, targets: list[str]) -> list[Output]:
    outputs: dict[Path, Output] = {}

    def add(out: Output) -> None:
        if out.path in outputs:
            raise SyncError(
                f"Dos fuentes escriben el mismo archivo {out.path}: "
                f"{outputs[out.path].origin} y {out.origin}"
            )
        outputs[out.path] = out

    for name in targets:
        target = mapping.get(name)
        for rule in target.rules:
            selected = [i for i in items if i.kind == rule.kind and i.allowed_for(name)]
            for out in _render_rule(target, rule, selected):
                add(out)
    return list(outputs.values())


def _render_rule(target: Target, rule: Rule, items: list[Item]) -> list[Output]:
    if rule.is_concat:
        if not items:
            return []
        sections = [_concat_section(rule, item, target.name) for item in items]
        data = (CONCAT_HEADER + "\n" + "\n\n".join(sections) + "\n").encode()
        origin = f"{len(items)} {rule.kind}s"
        return [Output(target.name, target.root / rule.dest, data, origin)]

    outputs = []
    for item in items:
        dest = target.root / rule.dest.format(name=item.name, kind=item.kind)
        if rule.is_dir:
            for file in item.files():
                rel = file.relative_to(item.path)
                data = file.read_bytes()
                if file.suffix.lower() == ".md":
                    text = data.decode("utf-8")
                    data = transforms.apply(rule.transform, text, item, target.name).encode()
                outputs.append(Output(target.name, dest / rel, data, str(file)))
        else:
            text = transforms.apply(rule.transform, item.body, item, target.name)
            outputs.append(Output(target.name, dest, text.encode(), str(item.main_file)))
    return outputs


def _concat_section(rule: Rule, item: Item, target: str) -> str:
    text = transforms.apply(rule.transform, item.body, item, target)
    meta, body = parse(text)
    lines = [f"## {item.name}"]
    if desc := meta.get("description") or item.meta.get("description"):
        lines.append(f"\n> {desc}")
    lines.append("\n" + body.strip())
    return "\n".join(lines)



def plan(
    outputs: list[Output],
    manifest: Manifest,
    targets: list[str],
    force: bool = False,
) -> list[Action]:
    actions = []
    produced = {o.path for o in outputs}

    for out in sorted(outputs, key=lambda o: (o.target, str(o.path))):
        new_hash = sha256_bytes(out.data)
        current = sha256_file(out.path)
        entry = manifest.get(out.path)
        if current is None:
            actions.append(Action("create", out.target, out.path, out.data))
        elif current == new_hash:
            actions.append(Action("unchanged", out.target, out.path, out.data))
        elif force or (entry and entry["sha256"] == current):
            actions.append(Action("update", out.target, out.path, out.data))
        elif entry:
            actions.append(Action("conflict", out.target, out.path, reason="editado a mano"))
        else:
            actions.append(Action("conflict", out.target, out.path, reason="no gestionado por aictl"))

    for name in targets:
        for path in sorted(manifest.paths_for(name)):
            if path not in produced:
                actions.append(_removal(path, name, manifest, force))
    return actions


def plan_removal(target: str, manifest: Manifest, force: bool = False) -> list[Action]:
    """Acciones para borrar todos los archivos gestionados de una AI (al quitarla)."""
    return [_removal(p, target, manifest, force) for p in sorted(manifest.paths_for(target))]


def _removal(path: Path, target: str, manifest: Manifest, force: bool) -> Action:
    current = sha256_file(path)
    if current is None:
        return Action("delete", target, path, reason="ya no existe")
    if force or current == manifest.get(path)["sha256"]:
        return Action("delete", target, path)
    return Action("keep", target, path, reason="editado a mano; no se borra")



def execute(actions: list[Action], manifest: Manifest, roots: dict[str, Path]) -> None:
    for action in actions:
        if action.op in ("create", "update", "unchanged"):
            if action.op != "unchanged":
                _atomic_write(action.path, action.data)
            manifest.record(action.path, action.target, sha256_bytes(action.data))
        elif action.op == "delete":
            action.path.unlink(missing_ok=True)
            manifest.forget(action.path)
            _prune_empty_dirs(action.path.parent, roots.get(action.target))
        elif action.op == "keep":
            manifest.forget(action.path)  


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".aictl")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _prune_empty_dirs(directory: Path, root: Path | None) -> None:
    if root is None:
        return
    root = root.resolve()
    current = directory.resolve()
    while current != root and root in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
