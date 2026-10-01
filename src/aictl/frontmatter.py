"""Parseo y serialización de frontmatter YAML en Markdown."""

from __future__ import annotations

import re

import yaml

_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)


def parse(text: str) -> tuple[dict, str]:
    """Devuelve (metadatos, cuerpo). Si no hay frontmatter válido, metadatos = {}."""
    match = _FM_RE.match(text)
    if not match:
        return {}, text
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(meta, dict):
        return {}, text
    return meta, text[match.end():]


def render(meta: dict, body: str) -> str:
    if not meta:
        return body
    dumped = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{dumped}\n---\n{body}"
