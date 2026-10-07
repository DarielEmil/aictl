"""Transformaciones de contenido aplicadas a los .md según la AI destino.

Cada transform recibe (texto, item, target) y devuelve el texto transformado.
`concat` no es una función: lo maneja `sync.build_outputs` agrupando items en un archivo.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from aictl import ALL_TARGETS
from aictl.frontmatter import parse, render
from aictl.sources.base import Item

Transform = Callable[[str, Item, str], str]

AICTL_KEYS = {"aictl", "targets", *ALL_TARGETS}

_EMBED_RE = re.compile(r"!\[\[([^\]]+)\]\]")
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]")


def _overrides(item: Item, target: str) -> dict:
    """Overrides por AI desde el frontmatter, p. ej. `opencode: {model: ...}`."""
    value = item.meta.get(target)
    return value if isinstance(value, dict) else {}


def strip_wikilinks(text: str, item: Item, target: str) -> str:
    """[[nota|alias]] → alias, [[nota#sección]] → nota, ![[embed]] → nota."""
    text = _EMBED_RE.sub(lambda m: m.group(1).split("|")[0].split("#")[0], text)
    return _WIKILINK_RE.sub(lambda m: (m.group(2) or m.group(1)).strip(), text)


def clean_frontmatter(text: str, item: Item, target: str) -> str:
    """Quita claves internas de aictl y aplica los overrides de la AI destino."""
    meta, body = parse(text)
    if not meta:
        return text
    cleaned = {k: v for k, v in meta.items() if k not in AICTL_KEYS}
    cleaned.update(_overrides(item, target))
    return render(cleaned, body)


def strip_frontmatter(text: str, item: Item, target: str) -> str:
    return parse(text)[1].lstrip("\n")


def opencode_frontmatter(text: str, item: Item, target: str) -> str:
    """OpenCode usa el nombre del archivo como nombre del agent y `mode: subagent`.

    `model` y `tools` de Claude no son compatibles, así que solo se mantienen si
    se definen en el override `opencode:` del frontmatter.
    """
    meta, body = parse(text)
    out = {"description": meta.get("description", item.meta.get("description", item.name))}
    out["mode"] = "subagent"
    out.update(_overrides(item, "opencode"))
    return render(out, body)


def kiro_steering(text: str, item: Item, target: str) -> str:
    """Archivo de steering de Kiro: frontmatter con `inclusion` (manual por defecto)."""
    _, body = parse(text)
    out = {"inclusion": "manual"}
    out.update(_overrides(item, "kiro"))
    return render(out, body.lstrip("\n"))


def to_kiro_json(text: str, item: Item, target: str) -> str:
    """Agent personalizado de Kiro (JSON) con el cuerpo del .md como prompt."""
    meta, body = parse(text)
    data = {
        "name": item.name,
        "description": meta.get("description", item.meta.get("description", "")),
        "prompt": body.strip(),
    }
    data.update(_overrides(item, "kiro"))
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    text = str(value)
    if "\n" in text and "'''" not in text:
        return "'''\n" + text + "'''" if text.endswith("\n") else "'''\n" + text + "\n'''"
    return json.dumps(text, ensure_ascii=False) 


def _toml_key(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else json.dumps(key, ensure_ascii=False)


def _toml_table(data: dict, prefix: str = "") -> list[str]:
    lines = [f"{_toml_key(k)} = {_toml_value(v)}" for k, v in data.items()
             if v is not None and not isinstance(v, dict)]
    for k, v in data.items():
        if isinstance(v, dict):
            name = f"{prefix}{_toml_key(k)}"
            lines += ["", f"[{name}]", *_toml_table(v, f"{name}.")]
    return lines


def to_codex_toml(text: str, item: Item, target: str) -> str:
    """Agent personalizado de Codex (TOML): el cuerpo del .md va en `developer_instructions`.

    `model` y `tools` de Claude no son compatibles, así que solo se incluyen campos
    de Codex (model, model_reasoning_effort, sandbox_mode...) vía el override `codex:`.
    """
    meta, body = parse(text)
    data = {
        "name": item.name,
        "description": meta.get("description", item.meta.get("description", "")),
        "developer_instructions": body.strip() + "\n",
    }
    data.update(_overrides(item, "codex"))
    return "\n".join(_toml_table(data)) + "\n"


def to_mdc(text: str, item: Item, target: str) -> str:
    """Regla de Cursor (.mdc): description, globs y alwaysApply."""
    meta, body = parse(text)
    out = {
        "description": meta.get("description", item.meta.get("description", "")),
        "globs": meta.get("globs", ""),
        "alwaysApply": bool(meta.get("alwaysApply", False)),
    }
    out.update(_overrides(item, "cursor"))
    return render(out, body)


TRANSFORMS: dict[str, Transform] = {
    "strip_wikilinks": strip_wikilinks,
    "clean_frontmatter": clean_frontmatter,
    "strip_frontmatter": strip_frontmatter,
    "opencode_frontmatter": opencode_frontmatter,
    "kiro_steering": kiro_steering,
    "to_kiro_json": to_kiro_json,
    "to_codex_toml": to_codex_toml,
    "to_mdc": to_mdc,
}

SPECIAL = {"concat"}


def apply(names: list[str], text: str, item: Item, target: str) -> str:
    text = clean_frontmatter(text, item, target)
    for name in names:
        if name in SPECIAL:
            continue
        text = TRANSFORMS[name](text, item, target)
    return text
