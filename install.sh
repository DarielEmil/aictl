#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${AICTL_BIN_DIR:-$HOME/.local/bin}"
DATA_DIR="${AICTL_DATA_DIR:-$HOME/.local/share/aictl}"
VENV_DIR="${AICTL_VENV_DIR:-$DATA_DIR/venv}"
META_FILE="$DATA_DIR/install.json"
METHOD="${AICTL_INSTALL_METHOD:-}"   # pipx | uv | venv (vacío = autodetectar)
MIN_PY="3.10"

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33mAviso:\033[0m %s\n' "$*"; }
fail()  { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

find_python() {
  for py in python3 python; do
    if command -v "$py" >/dev/null 2>&1 &&
       "$py" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
      echo "$py"; return 0
    fi
  done
  return 1
}

uninstall() {
  info "Desinstalando aictl"
  if command -v pipx >/dev/null 2>&1 && pipx list --short 2>/dev/null | grep -q '^aictl '; then
    pipx uninstall aictl
  fi
  if command -v uv >/dev/null 2>&1 && uv tool list 2>/dev/null | grep -q '^aictl '; then
    uv tool uninstall aictl
  fi
  if [ -L "$BIN_DIR/aictl" ] && [[ "$(readlink "$BIN_DIR/aictl")" == "$VENV_DIR"* ]]; then
    rm -f "$BIN_DIR/aictl"
  fi
  rm -rf "$VENV_DIR"
  rm -f "$META_FILE"
  info "Listo. La configuración en ~/.config/aictl se conserva (bórrala a mano si quieres)."
}

ensure_path() {
  case ":$PATH:" in
    *":$BIN_DIR:"*) return 0 ;;
  esac
  local rc
  case "${SHELL##*/}" in
    zsh)  rc="$HOME/.zshrc" ;;
    bash) rc="$HOME/.bashrc" ;;
    *)    rc="" ;;
  esac
  local line="export PATH=\"$BIN_DIR:\$PATH\""
  if [ -n "$rc" ] && [ -t 0 ]; then
    read -r -p "$BIN_DIR no está en tu PATH. ¿Añadirlo a $rc? [S/n] " answer
    if [[ -z "$answer" || "$answer" =~ ^[sSyY] ]]; then
      grep -qxF "$line" "$rc" 2>/dev/null || printf '\n# aictl\n%s\n' "$line" >> "$rc"
      info "Añadido a $rc. Abre una terminal nueva o ejecuta: source $rc"
      return 0
    fi
  fi
  warn "$BIN_DIR no está en tu PATH. Añade esta línea a tu shell rc:"
  echo "    $line"
}

detect_method() {
  if command -v pipx >/dev/null 2>&1; then echo pipx
  elif command -v uv >/dev/null 2>&1; then echo uv
  else echo venv
  fi
}

# Guarda de dónde y cómo se instaló, para que `aictl upgrade` pueda repetirlo.
write_meta() {
  mkdir -p "$DATA_DIR"
  "$1" - "$META_FILE" "$PROJECT_DIR" "$METHOD" "$BIN_DIR" "$VENV_DIR" <<'PY'
import json, sys
from datetime import datetime, timezone
path, source, method, bin_dir, venv_dir = sys.argv[1:]
data = {
    "source_dir": source,
    "method": method,
    "bin_dir": bin_dir,
    "venv_dir": venv_dir,
    "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY
}

install() {
  local py
  py="$(find_python)" || fail "Se necesita Python >= $MIN_PY"
  [ -n "$METHOD" ] || METHOD="$(detect_method)"
  info "Instalando aictl desde $PROJECT_DIR"

  case "$METHOD" in
    pipx)
      command -v pipx >/dev/null 2>&1 || fail "pipx no está instalado"
      info "Usando pipx"
      pipx install --force "$PROJECT_DIR"
      ;;
    uv)
      command -v uv >/dev/null 2>&1 || fail "uv no está instalado"
      info "Usando uv tool"
      uv tool install --force --reinstall "$PROJECT_DIR"
      ;;
    venv) install_venv "$py" ;;
    *) fail "Método de instalación desconocido: $METHOD (pipx | uv | venv)" ;;
  esac

  write_meta "$py"
  ensure_path
  if command -v aictl >/dev/null 2>&1 || [ -x "$BIN_DIR/aictl" ]; then
    info "Instalado: $("$BIN_DIR/aictl" --version 2>/dev/null || aictl --version)"
    [ -n "${AICTL_UPGRADING:-}" ] || info "Siguiente paso: aictl init"
  fi
}

install_venv() {
  local py="$1"
  info "Usando un venv en $VENV_DIR"
  "$py" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
  "$VENV_DIR/bin/python" -m pip install --quiet --upgrade "$PROJECT_DIR"
  mkdir -p "$BIN_DIR"
  ln -sf "$VENV_DIR/bin/aictl" "$BIN_DIR/aictl"
}

case "${1:-}" in
  --uninstall|uninstall) uninstall ;;
  ""|--install)          install ;;
  -h|--help)             echo "Uso: ./install.sh [--uninstall]" ;;
  *)                     fail "Opción desconocida: $1 (usa --help)" ;;
esac
