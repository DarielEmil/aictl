# aictl Wiki (Español)

`aictl` te permite definir tus **agents** y **skills** una sola vez en tu bóveda de **Obsidian** y sincronizarlos con **Claude, OpenCode, Codex, Antigravity, Kiro y Cursor**.

## Instalación

```bash
./install.sh              # instala/actualiza `aictl` en ~/.local/bin (pipx → uv → venv)
./install.sh --uninstall  # desinstala (mantiene ~/.config/aictl)
```

Requiere Python >= 3.10.

## Uso

```bash
aictl init      # solicita ruta del vault, carpetas de agents/skills y AIs objetivo
aictl sync      # copia agents/skills del vault hacia cada AI seleccionada
aictl update    # actualiza tu configuración: rutas, carpetas y AIs
aictl upgrade   # actualiza la herramienta (git pull + reinstall)
aictl status    # muestra configuración actual y último sync
aictl doctor    # valida acceso al vault y permisos de escritura en destinos
aictl mapping   # muestra el YAML de mapeo en uso (--export para personalizar)
```

Sin flags, `init` y `update` funcionan en modo interactivo.

## Estructura esperada en Obsidian

```text
<vault>/
└── AI-Config/
    ├── agents/
    │   └── check-reviewer/
    │       └── code-reviewer.md
    └── skills/
        └── pdf-tools/
            ├── SKILL.md
            └── scripts/extract.py
```

- El nombre del agent/skill es el nombre de la carpeta (salvo `name:` en frontmatter).
- Si un agent tiene más de un `.md`, se considera error.
- Si un skill no tiene `SKILL.md`, se ignora.

## Mapeo de destinos

El archivo base es `src/aictl/data/targets.yaml` y define para cada AI:

- Carpeta de destino de agents
- Carpeta de destino de skills
- Transformaciones aplicadas al contenido

Puedes exportarlo y personalizarlo con:

```bash
aictl mapping --export
```

## Validaciones de acceso

`init`, `update` (cuando cambias rutas o AIs) y `doctor` comprueban:

- Que el vault y las carpetas configuradas existen y se pueden listar.
- Que los archivos de agents/skills se pueden leer.
- Que los destinos de cada AI permiten escritura.

Si hay errores, `init`/`update` piden confirmación antes de guardar.

## Seguridad de archivos

`aictl` registra lo que escribe en `~/.config/aictl/manifest.json`.

Durante `sync`:

- Solo sobrescribe archivos gestionados por `aictl` que no hayan sido editados manualmente.
- Marca conflictos cuando el archivo ya existía sin gestión o fue modificado manualmente.
- Si eliminas un agent/skill en el vault, elimina su copia gestionada.
- `--force` permite sobrescribir conflictos.

## Desarrollo

```bash
uv venv && uv pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check src tests
```
