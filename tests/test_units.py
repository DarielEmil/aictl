import json

import pytest

from aictl import mapping, transforms
from aictl.frontmatter import parse
from aictl.mapping import MappingError
from aictl.sources import ObsidianSource, SourceError
from aictl.sources.base import Item


def _source(vault):
    return ObsidianSource(vault, vault / "AI-Config/agents", vault / "AI-Config/skills")


def test_obsidian_source_reads_agents_and_skills(vault):
    items = {(i.kind, i.name): i for i in _source(vault).items()}
    assert set(items) == {
        ("agent", "code-reviewer"),
        ("agent", "claude-only"),
        ("skill", "pdf-tools"),
    }  # borrador (aictl: false) y drafts (sin SKILL.md) se ignoran
    skill = items[("skill", "pdf-tools")]
    assert [p.name for p in skill.files()] == ["SKILL.md", "extract.py"]


def test_agent_name_comes_from_folder(vault):
    folder = vault / "AI-Config/agents/check-reviewer"
    folder.mkdir()
    (folder / "code-reviewer.md").write_text("---\ndescription: d\n---\nCuerpo\n")
    items = {i.name: i for i in _source(vault).items() if i.kind == "agent"}
    assert items["check-reviewer"].path == folder / "code-reviewer.md"


def test_agent_folder_with_several_md_is_an_error(vault):
    (vault / "AI-Config/agents/claude-only/otro.md").write_text("x")
    with pytest.raises(SourceError, match="único .md"):
        _source(vault).items()


def test_loose_md_in_agents_root_is_ignored(vault):
    (vault / "AI-Config/agents/suelto.md").write_text("---\ndescription: d\n---\nx\n")
    assert "suelto" not in {i.name for i in _source(vault).items()}


def test_targets_restriction(vault):
    items = {i.name: i for i in _source(vault).items()}
    assert items["claude-only"].allowed_for("claude")
    assert not items["claude-only"].allowed_for("codex")
    assert items["code-reviewer"].allowed_for("codex")


def test_strip_wikilinks():
    item = Item("agent", "x", None)
    text = "Ver [[Nota|alias]], [[Otra#Sección]], [[Simple]] y ![[img.png]]."
    assert transforms.strip_wikilinks(text, item, "claude") == "Ver alias, Otra, Simple y img.png."


def test_clean_frontmatter_removes_internal_keys_and_applies_overrides():
    text = "---\nname: a\ntargets: [claude]\nopencode:\n  model: m\n---\nbody\n"
    item = Item("agent", "a", None, parse(text)[0], text)
    meta, body = parse(transforms.clean_frontmatter(text, item, "opencode"))
    assert meta == {"name": "a", "model": "m"}
    assert body == "body\n"


def test_kiro_json():
    text = "---\ndescription: d\n---\nPrompt\n"
    item = Item("agent", "a", None, parse(text)[0], text)
    data = json.loads(transforms.to_kiro_json(text, item, "kiro"))
    assert data == {"name": "a", "description": "d", "prompt": "Prompt"}


def test_default_mapping_is_valid():
    maps = mapping.parse(mapping.default_text())
    assert set(maps.targets) == {"claude", "opencode", "codex", "antigravity", "kiro", "cursor"}


@pytest.mark.parametrize(
    "rule, message",
    [
        ("{kind: agent, dest: 'agents/'}", "solo las skills"),
        ("{kind: agent, dest: 'AGENTS.md'}", "{name}"),
        ("{kind: agent, dest: '{name}.md', transform: [concat]}", "único archivo"),
        ("{kind: agent, dest: '{name}.md', transform: [nope]}", "desconocido"),
        ("{kind: agent, dest: '../{name}.md'}", "relativo"),
        ("{kind: tool, dest: '{name}.md'}", "kind"),
    ],
)
def test_mapping_validation(rule, message):
    with pytest.raises(MappingError, match=message):
        mapping.parse(f"targets:\n  x:\n    root: /tmp\n    rules:\n      - {rule}\n")
