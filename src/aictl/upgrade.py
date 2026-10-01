"""Actualización de la propia herramienta: trae el código nuevo y reinstala.

Nunca toca la configuración del usuario (~/.config/aictl): solo el repo de
origen (git pull) y la instalación del comando (install.sh).
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class UpgradeError(Exception):
    pass


def data_dir() -> Path:
    if env := os.environ.get("AICTL_DATA_DIR"):
        return Path(env).expanduser()
    return Path("~/.local/share/aictl").expanduser()


def meta_path() -> Path:
    return data_dir() / "install.json"


@dataclass
class InstallInfo:
    source_dir: Path
    method: str
    bin_dir: str
    venv_dir: str

    @property
    def installer(self) -> Path:
        return self.source_dir / "install.sh"


def load_install_info() -> InstallInfo:
    path = meta_path()
    if not path.is_file():
        raise UpgradeError(
            f"No se encontró {path}. Ejecuta `./install.sh` una vez desde el repo de aictl "
            "para que `aictl upgrade` sepa de dónde actualizarse."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    info = InstallInfo(
        source_dir=Path(data["source_dir"]),
        method=data.get("method", ""),
        bin_dir=data.get("bin_dir", ""),
        venv_dir=data.get("venv_dir", ""),
    )
    if not info.installer.is_file():
        raise UpgradeError(
            f"El repo de origen ya no está en {info.source_dir}. "
            "Ejecuta `./install.sh` desde su nueva ubicación."
        )
    return info


def _git(source: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(source), *args], capture_output=True, text=True, check=check
    )


def is_git_repo(source: Path) -> bool:
    return (source / ".git").exists()


def current_commit(source: Path) -> str | None:
    result = _git(source, "rev-parse", "--short", "HEAD", check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def upstream(source: Path) -> str | None:
    result = _git(source, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def has_local_changes(source: Path) -> bool:
    return bool(_git(source, "status", "--porcelain", "--untracked-files=no").stdout.strip())


def pull(source: Path) -> str:
    """git pull --ff-only; nunca crea merges ni pisa cambios locales."""
    result = _git(source, "pull", "--ff-only", check=False)
    if result.returncode != 0:
        raise UpgradeError(
            "No se pudo hacer `git pull --ff-only` en "
            f"{source}:\n{(result.stderr or result.stdout).strip()}"
        )
    return result.stdout.strip()


def pending_commits(source: Path) -> list[str]:
    """Commits del remoto que aún no están en local (hace git fetch)."""
    fetch = _git(source, "fetch", "--quiet", check=False)
    if fetch.returncode != 0:
        raise UpgradeError(f"git fetch falló: {fetch.stderr.strip()}")
    return changelog(source, "HEAD", "@{u}")


def changelog(source: Path, before: str, after: str) -> list[str]:
    result = _git(source, "log", "--oneline", f"{before}..{after}", check=False)
    return result.stdout.splitlines() if result.returncode == 0 else []


def reinstall(info: InstallInfo) -> None:
    """Ejecuta install.sh con el mismo método y rutas de la instalación original."""
    env = {
        **os.environ,
        "AICTL_UPGRADING": "1",
        "AICTL_INSTALL_METHOD": info.method,
        "AICTL_DATA_DIR": str(data_dir()),
    }
    if info.bin_dir:
        env["AICTL_BIN_DIR"] = info.bin_dir
    if info.venv_dir:
        env["AICTL_VENV_DIR"] = info.venv_dir
    result = subprocess.run(
        ["bash", str(info.installer)], env=env, stdin=subprocess.DEVNULL, check=False
    )
    if result.returncode != 0:
        raise UpgradeError(f"install.sh terminó con código {result.returncode}")
