"""Registro de los archivos que aictl ha escrito (ruta → target + sha256).

Sirve para saber qué archivos se pueden sobrescribir o borrar con seguridad:
solo los que aictl creó y que nadie ha editado a mano desde entonces.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from aictl.config import config_dir


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str | None:
    try:
        return sha256_bytes(path.read_bytes())
    except FileNotFoundError:
        return None


def manifest_path() -> Path:
    return config_dir() / "manifest.json"


@dataclass
class Manifest:
    files: dict[str, dict] = field(default_factory=dict)  # ruta absoluta → {target, sha256}
    last_sync: str | None = None

    def get(self, path: Path) -> dict | None:
        return self.files.get(str(path))

    def record(self, path: Path, target: str, digest: str) -> None:
        self.files[str(path)] = {"target": target, "sha256": digest}

    def forget(self, path: Path) -> None:
        self.files.pop(str(path), None)

    def paths_for(self, target: str) -> list[Path]:
        return [Path(p) for p, e in self.files.items() if e.get("target") == target]

    def targets(self) -> set[str]:
        return {e.get("target") for e in self.files.values()}

    def touch(self) -> None:
        self.last_sync = datetime.now(timezone.utc).isoformat(timespec="seconds")


def load() -> Manifest:
    path = manifest_path()
    if not path.is_file():
        return Manifest()
    data = json.loads(path.read_text(encoding="utf-8"))
    return Manifest(files=data.get("files", {}), last_sync=data.get("last_sync"))


def save(manifest: Manifest) -> None:
    path = manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "last_sync": manifest.last_sync, "files": dict(sorted(manifest.files.items()))}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
