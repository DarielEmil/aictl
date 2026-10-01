import json
import subprocess

import pytest
from typer.testing import CliRunner

from aictl import config
from aictl.cli import app

runner = CliRunner()

# install.sh falso: registra con qué método y variables se le llamó.
FAKE_INSTALLER = """#!/usr/bin/env bash
echo "$AICTL_INSTALL_METHOD $AICTL_UPGRADING $AICTL_BIN_DIR" > "$AICTL_DATA_DIR/reinstalled"
"""


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def commit(repo, name, content):
    (repo / name).write_text(content)
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", f"cambia {name}")


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setenv("AICTL_DATA_DIR", str(d))
    return d


def write_meta(data_dir, source, method="uv"):
    (data_dir / "install.json").write_text(
        json.dumps({"source_dir": str(source), "method": method, "bin_dir": "/x/bin", "venv_dir": ""})
    )


@pytest.fixture
def repos(tmp_path):
    """Remoto bare + clon de origen (el instalado) + otro clon que publica cambios."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    publisher = tmp_path / "publisher"
    subprocess.run(["git", "clone", "-q", str(remote), str(publisher)], check=True)
    (publisher / "install.sh").write_text(FAKE_INSTALLER)
    commit(publisher, "VERSION", "1\n")
    git(publisher, "push", "-q", "origin", "HEAD:main")
    source = tmp_path / "source"
    subprocess.run(["git", "clone", "-q", str(remote), str(source)], check=True)
    return source, publisher


def test_upgrade_pulls_and_reinstalls_without_touching_config(cfg, data_dir, repos):
    source, publisher = repos
    write_meta(data_dir, source)
    commit(publisher, "VERSION", "2\n")
    git(publisher, "push", "-q", "origin", "HEAD:main")
    config_before = config.config_path().read_text()

    result = runner.invoke(app, ["upgrade"])
    assert result.exit_code == 0, result.output
    assert (source / "VERSION").read_text() == "2\n"
    assert "cambia VERSION" in result.output
    assert (data_dir / "reinstalled").read_text().split() == ["uv", "1", "/x/bin"]
    assert config.config_path().read_text() == config_before


def test_upgrade_check_lists_pending_without_installing(cfg, data_dir, repos):
    source, publisher = repos
    write_meta(data_dir, source)
    commit(publisher, "VERSION", "2\n")
    git(publisher, "push", "-q", "origin", "HEAD:main")

    result = runner.invoke(app, ["upgrade", "--check"])
    assert result.exit_code == 0, result.output
    assert "1" in result.output and "cambia VERSION" in result.output
    assert (source / "VERSION").read_text() == "1\n"
    assert not (data_dir / "reinstalled").exists()


def test_upgrade_without_remote_reinstalls_local_code(cfg, data_dir, tmp_path):
    source = tmp_path / "local"
    source.mkdir()
    (source / "install.sh").write_text(FAKE_INSTALLER)
    write_meta(data_dir, source, method="venv")

    result = runner.invoke(app, ["upgrade"])
    assert result.exit_code == 0, result.output
    assert "código local" in result.output
    assert (data_dir / "reinstalled").read_text().startswith("venv")


def test_upgrade_without_install_metadata_fails(data_dir):
    result = runner.invoke(app, ["upgrade"])
    assert result.exit_code == 1
    assert "install.sh" in result.output
