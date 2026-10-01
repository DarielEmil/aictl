import shutil
from pathlib import Path

import pytest

from aictl import config
from aictl.config import Config, SourceConfig

FIXTURE_VAULT = Path(__file__).parent / "fixtures" / "vault"


@pytest.fixture
def home(tmp_path, monkeypatch):
    """HOME aislado: todos los destinos (~/.claude, ...) y la config van a tmp_path."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("AICTL_CONFIG_DIR", raising=False)
    return home


@pytest.fixture
def vault(tmp_path):
    dest = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, dest)
    return dest


@pytest.fixture
def cfg(home, vault):
    c = Config(
        source=SourceConfig(vault_path=str(vault)),  # carpetas por defecto: AI-Config/...
        targets=["claude", "opencode", "codex", "antigravity", "cursor", "kiro"],
    )
    config.save(c)
    return c
