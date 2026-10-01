# aictl

Define tus **agents** y **skills** de IA una sola vez en tu vault de **Obsidian** y sincronízalos
con las herramientas que uses: **Claude Code, OpenCode, Codex, Antigravity, Kiro y Cursor**.

## Instalación

```bash
./install.sh              # instala/actualiza `aictl` en ~/.local/bin (pipx → uv → venv)
./install.sh --uninstall  # desinstala (conserva ~/.config/aictl)
```

Requiere Python ≥ 3.10.

## Uso

```bash
aictl init      # pide ruta del vault, carpetas de agents/skills y las AIs a configurar
aictl sync      # copia agents/skills del vault a cada AI seleccionada
aictl update    # cambia TU CONFIGURACIÓN: ruta del vault, carpetas, AIs
aictl upgrade   # actualiza la herramienta aictl (git pull + reinstalar)
aictl status    # configuración actual y último sync
aictl doctor    # verifica vault, mapeo y permisos
aictl mapping   # muestra el YAML de mapeo en uso (--export para personalizarlo)
```

Opciones útiles:

| Comando | Opciones |
|---|---|
| `init` | `--vault`, `--agents-dir`, `--skills-dir`, `--targets claude,codex`, `--force`, `--sync/--no-sync` |
| `update` | `--vault`, `--agents-dir`, `--skills-dir`, `--add`, `--remove`, `--clean/--no-clean` |
| `sync` | `--dry-run`, `--target claude`, `--force`, `--verbose` |
| `upgrade` | `--check` (solo mira si hay cambios), `--no-pull` (reinstala el código local) |

Sin flags, `init` y `update` son interactivos.

## Actualizar aictl

`aictl upgrade` actualiza la propia herramienta sin que tengas que ir al repo:

1. Hace `git pull --ff-only` en el repo desde el que instalaste (nunca crea merges; si hay
   conflicto con cambios locales, se detiene sin tocar nada).
2. Vuelve a ejecutar `install.sh` con el mismo método (pipx / uv / venv) y las mismas rutas.

No modifica tu configuración (`~/.config/aictl/`: `config.yaml`, `targets.yaml`, `manifest.json`).
Si el repo no tiene remoto, reinstala el código local (útil si editas aictl tú mismo).
`install.sh` guarda de dónde se instaló en `~/.local/share/aictl/install.json`.

## Formato en Obsidian

```
<vault>/
└── AI-Config/
    ├── agents/
    │   └── check-reviewer/             # un agent = una carpeta con un único .md
    │       └── code-reviewer.md        #   nombre del agent: "check-reviewer"
    └── skills/
        └── pdf-tools/                  # una skill = una carpeta con SKILL.md
            ├── SKILL.md                #   (+ archivos auxiliares, se copian todos)
            └── scripts/extract.py
```

- El nombre del agent/skill es el de su carpeta, salvo que el frontmatter defina `name:`.
- Una carpeta de agent con más de un `.md` es un error; una carpeta de skill sin `SKILL.md` se ignora.
- `AI-Config/agents` y `AI-Config/skills` son las carpetas por defecto (configurables en `init`/`update`).

```markdown
---
name: code-reviewer            # opcional (por defecto el nombre de la carpeta)
description: Revisa cambios de código
model: sonnet
targets: [claude, opencode]    # opcional: limita a qué AIs se copia
aictl: false                   # opcional: excluye el archivo
opencode:                      # opcional: overrides de frontmatter para una AI concreta
  model: anthropic/claude-sonnet-4-5
---
Instrucciones del agent. Los [[wikilinks]] se convierten en texto plano.
```

Las claves `targets`, `aictl` y los overrides por AI nunca llegan a los archivos generados.

## Mapeo (YAML)

`src/aictl/data/targets.yaml` define, por AI, la carpeta raíz y qué copiar dónde.
Para personalizarlo: `aictl mapping --export` → edita `~/.config/aictl/targets.yaml`
(o apunta `mapping_file` en `config.yaml` a otro archivo).

| AI | Agents | Skills |
|---|---|---|
| claude | `~/.claude/agents/{name}.md` | `~/.claude/skills/{name}/` |
| opencode | `~/.config/opencode/agents/{name}.md` | `~/.config/opencode/skills/{name}/` |
| codex | `~/.codex/AGENTS.md` (concatenado) | `~/.codex/skills/{name}/` |
| antigravity | `~/.gemini/GEMINI.md` (concatenado) | `~/.gemini/antigravity/skills/{name}/` |
| kiro | `~/.kiro/agents/{name}.json` | `~/.kiro/skills/{name}/` |
| cursor | `~/.cursor/agents/{name}.md` | `~/.cursor/skills/{name}/` |

Transforms disponibles: `strip_wikilinks`, `strip_frontmatter`, `opencode_frontmatter`,
`kiro_steering` (para usar `~/.kiro/steering/`), `to_kiro_json`, `to_mdc`, `concat`.

> Las rutas globales de cada herramienta cambian con sus versiones; si alguna no coincide con
> la tuya, ajústala en tu `targets.yaml`.

## Seguridad de los archivos

aictl guarda en `~/.config/aictl/manifest.json` cada archivo que escribe con su hash. En `sync`:

- Solo sobrescribe archivos que **él creó** y que **no se han editado a mano**.
- Un archivo existente no gestionado (p. ej. tu `~/.codex/AGENTS.md`) o editado a mano se marca
  como **conflicto** y no se toca. `--force` lo sobrescribe.
- Si borras un agent/skill del vault, se elimina su copia gestionada (las carpetas vacías también).
- `aictl update --remove X --clean` borra solo los archivos gestionados de esa AI.

## Desarrollo

```bash
uv venv && uv pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check src tests
```
