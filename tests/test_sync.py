import json
import shutil

from typer.testing import CliRunner

from aictl import config, manifest
from aictl.cli import app

runner = CliRunner()


def run(*args):
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result


def test_sync_writes_all_targets(cfg, home):
    run("sync")

    claude = home / ".claude"
    assert (claude / "agents/code-reviewer.md").is_file()
    assert (claude / "agents/claude-only.md").is_file()
    assert (claude / "skills/pdf-tools/SKILL.md").is_file()
    assert (claude / "skills/pdf-tools/scripts/extract.py").read_text() == 'print("extract")\n'
    reviewer = (claude / "agents/code-reviewer.md").read_text()
    assert "[[" not in reviewer and "estilo" in reviewer
    assert "opencode:" not in reviewer  # claves internas eliminadas

    opencode = (home / ".config/opencode/agents/code-reviewer.md").read_text()
    assert "mode: subagent" in opencode and "model: anthropic/claude-sonnet-4-5" in opencode
    assert not (home / ".config/opencode/agents/claude-only.md").exists()

    agents_md = (home / ".codex/AGENTS.md").read_text()
    assert "## code-reviewer" in agents_md and "claude-only" not in agents_md
    assert (home / ".codex/skills/pdf-tools/SKILL.md").is_file()
    assert (home / ".gemini/GEMINI.md").is_file()

    kiro = json.loads((home / ".kiro/agents/code-reviewer.json").read_text())
    assert kiro["name"] == "code-reviewer"
    assert (home / ".kiro/skills/pdf-tools/SKILL.md").is_file()
    assert (home / ".cursor/agents/code-reviewer.md").is_file()

    assert manifest.load().last_sync is not None


def test_dry_run_writes_nothing(cfg, home):
    result = run("sync", "--dry-run")
    assert "Dry-run" in result.output
    assert not (home / ".claude").exists()
    assert not manifest.manifest_path().exists()


def test_second_sync_is_idempotent(cfg, home):
    run("sync")
    result = run("sync")
    assert "sin cambios" in result.output
    assert "creado" not in result.output


def test_unmanaged_file_is_a_conflict(cfg, home):
    existing = home / ".codex/AGENTS.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("mis instrucciones\n")

    result = run("sync")
    assert "conflicto" in result.output
    assert existing.read_text() == "mis instrucciones\n"

    run("sync", "--force")
    assert "code-reviewer" in existing.read_text()


def test_hand_edited_file_is_not_overwritten(cfg, home, vault):
    run("sync")
    target = home / ".claude/agents/code-reviewer.md"
    target.write_text("editado a mano\n")
    (vault / "AI-Config/agents/code-reviewer/code-reviewer.md").write_text("---\ndescription: nuevo\n---\nNuevo\n")

    result = run("sync")
    assert "editado a mano" in result.output
    assert target.read_text() == "editado a mano\n"


def test_source_change_updates_and_orphans_are_removed(cfg, home, vault):
    run("sync")
    (vault / "AI-Config/agents/code-reviewer/code-reviewer.md").write_text("---\ndescription: nuevo\n---\nNuevo\n")
    (vault / "AI-Config/agents/claude-only/claude-only.md").unlink()
    shutil.rmtree(vault / "AI-Config/skills/pdf-tools")

    result = run("sync")
    assert "actualizado" in result.output and "eliminado" in result.output
    assert "Nuevo" in (home / ".claude/agents/code-reviewer.md").read_text()
    assert not (home / ".claude/agents/claude-only.md").exists()
    assert not (home / ".claude/skills/pdf-tools").exists()  # carpetas vacías eliminadas
    assert (home / ".claude").is_dir()


def test_sync_single_target(cfg, home):
    run("sync", "--target", "claude")
    assert (home / ".claude/agents/code-reviewer.md").exists()
    assert not (home / ".codex").exists()


def test_init_non_interactive(home, vault):
    run(
        "init",
        "--vault", str(vault),
        "--agents-dir", "AI-Config/agents",
        "--skills-dir", "AI-Config/skills",
        "--targets", "claude,codex",
        "--no-sync",
    )
    cfg = config.load()
    assert cfg.targets == ["claude", "codex"]
    assert cfg.source.agents_dir == "AI-Config/agents"

    result = runner.invoke(app, ["init", "--vault", str(vault), "--targets", "claude"])
    assert result.exit_code == 1 and "aictl update" in result.output


def test_update_remove_target_with_clean(cfg, home):
    run("sync")
    assert (home / ".kiro/agents/code-reviewer.json").exists()

    run("update", "--remove", "kiro", "--clean")
    assert "kiro" not in config.load().targets
    assert not (home / ".kiro/agents/code-reviewer.json").exists()
    assert not manifest.load().paths_for("kiro")


def test_update_remove_target_keeps_files_by_default(cfg, home):
    run("sync")
    run("update", "--remove", "cursor", "--add", "claude")
    assert (home / ".cursor/agents/code-reviewer.md").exists()


def test_update_vault_path(cfg, home, vault, tmp_path):
    other = tmp_path / "otro"
    shutil.copytree(vault, other)
    result = run("update", "--vault", str(other))
    assert "Comprobando acceso" in result.output
    assert config.load().source.vault_path == str(other)


def test_update_rejects_vault_without_agents_or_skills(cfg, tmp_path):
    empty = tmp_path / "vacio"
    empty.mkdir()
    result = runner.invoke(app, ["update", "--vault", str(empty)])
    assert result.exit_code == 1
    assert "ninguna de las carpetas" in result.output
    assert config.load().source.vault_path == cfg.source.vault_path  # no se guardó


def test_init_rejects_unreadable_vault(home, tmp_path):
    result = runner.invoke(app, ["init", "--vault", str(tmp_path / "no-existe"), "--targets", "claude"])
    assert result.exit_code == 1
    assert "no existe" in result.output
    assert not config.exists()


def test_init_warns_about_empty_folders(home, tmp_path):
    vault = tmp_path / "drive"
    (vault / "AI-Config/agents").mkdir(parents=True)
    (vault / "AI-Config/skills/sin-skill-md").mkdir(parents=True)
    result = run("init", "--vault", str(vault), "--targets", "claude", "--no-sync")
    assert "está vacía" in result.output and "Disponible sin conexión" in result.output
    assert "sin SKILL.md" in result.output
    assert "ningún agent ni skill" in result.output


def test_doctor_reports_readable_vault_and_writable_targets(cfg):
    result = run("doctor")
    assert "2 agents y 1 skills encontrados y legibles" in result.output
    assert "claude: se puede escribir" in result.output


def test_unknown_target_rejected(cfg):
    result = runner.invoke(app, ["update", "--add", "chatgpt"])
    assert result.exit_code == 1 and "desconocidas" in result.output
