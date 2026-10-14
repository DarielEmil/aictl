# aictl

Define your AI **agents** and **skills** once in your **Obsidian** vault and sync them
with the tools you use: **Claude Code, OpenCode, Codex, Antigravity, Kiro, and Cursor**.

## Installation

```bash
./install.sh              # installs/updates `aictl` in ~/.local/bin (pipx → uv → venv)
./install.sh --uninstall  # uninstalls (keeps ~/.config/aictl)
```

Requires Python ≥ 3.10.

## Usage

```bash
aictl init      # asks for vault path, agents/skills folders, and AIs to configure
aictl sync      # copies agents/skills from the vault to each selected AI
aictl update    # changes YOUR CONFIGURATION: vault path, folders, AIs
aictl upgrade   # updates the aictl tool itself (git pull + reinstall)
aictl status    # current configuration and last sync
aictl doctor    # checks that the vault can be read and AI locations can be written
aictl mapping   # shows the mapping YAML in use (--export to customize it)
```

Useful options:

| Command | Options |
|---|---|
| `init` | `--vault`, `--agents-dir`, `--skills-dir`, `--targets claude,codex`, `--force`, `--sync/--no-sync` |
| `update` | `--vault`, `--agents-dir`, `--skills-dir`, `--add`, `--remove`, `--clean/--no-clean` |
| `sync` | `--dry-run`, `--target claude`, `--force`, `--verbose` |
| `upgrade` | `--check` (only checks for changes), `--no-pull` (reinstalls local code) |

Without flags, `init` and `update` are interactive.

## Updating aictl

`aictl upgrade` updates the tool itself so you do not need to go to the repo:

1. It runs `git pull --ff-only` in the repo you installed from (it never creates merges; if there
   are local-change conflicts, it stops without touching anything).
2. It runs `install.sh` again using the same method (pipx / uv / venv) and the same paths.

It does not modify your configuration (`~/.config/aictl/`: `config.yaml`, `targets.yaml`, `manifest.json`).
If the repo has no remote, it reinstalls local code (useful if you edit aictl yourself).
`install.sh` saves the install source in `~/.local/share/aictl/install.json`.

## Obsidian format

```
<vault>/
└── AI-Config/
    ├── agents/
    │   └── check-reviewer/             # one agent = one folder with a single .md
    │       └── code-reviewer.md        #   agent name: "check-reviewer"
    └── skills/
        └── pdf-tools/                  # one skill = one folder with SKILL.md
            ├── SKILL.md                #   (+ auxiliary files, all are copied)
            └── scripts/extract.py
```

- The agent/skill name is the folder name, unless frontmatter defines `name:`.
- An agent folder with more than one `.md` is an error; a skill folder without `SKILL.md` is ignored.
- `AI-Config/agents` and `AI-Config/skills` are the default folders (configurable in `init`/`update`).

```markdown
---
name: code-reviewer            # optional (defaults to folder name)
description: Review code changes
model: sonnet
targets: [claude, opencode]    # optional: restricts which AIs receive this copy
aictl: false                   # optional: excludes the file
opencode:                      # optional: frontmatter overrides for a specific AI
  model: anthropic/claude-sonnet-4-5
---
Agent instructions. [[wikilinks]] are converted to plain text.
```

The `targets`, `aictl`, and per-AI override keys are never written to generated files.

## Mapping (YAML)

`src/aictl/data/targets.yaml` defines, per AI, the root folder and what gets copied where.
To customize it: `aictl mapping --export` → edit `~/.config/aictl/targets.yaml`
(or point `mapping_file` in `config.yaml` to another file).

| AI | Agents | Skills |
|---|---|---|
| claude | `~/.claude/agents/{name}.md` | `~/.claude/skills/{name}/` |
| opencode | `~/.config/opencode/agents/{name}.md` | `~/.config/opencode/skills/{name}/` |
| codex | `~/.codex/agents/{name}.toml` | `~/.codex/skills/{name}/` |
| antigravity | `~/.gemini/config/agents/{name}/agent.md` | `~/.gemini/config/skills/{name}/` |
| kiro | `~/.kiro/agents/{name}.json` | `~/.kiro/skills/{name}/` |
| cursor | `~/.cursor/agents/{name}.md` | `~/.cursor/skills/{name}/` |

Available transforms: `strip_wikilinks`, `strip_frontmatter`, `opencode_frontmatter`,
`kiro_steering` (to use `~/.kiro/steering/`), `to_kiro_json`, `to_codex_toml`, `to_mdc`, `concat`.

> Global paths for each tool may change across versions; if one does not match your setup,
> adjust it in your `targets.yaml`.

## Access checks

`init`, `update` (when changing the vault or adding AIs), and `doctor` check before saving:

- The vault and agents/skills folders exist and **can be listed** (detects macOS blocking in
  Google Drive/iCloud and explains how to grant terminal permission).
- All files in each agent/skill can be **read**.
- Warns about empty folders (Drive not synced), agents without `.md`, and skills without `SKILL.md`.
- Each AI folder can be **written** to (real check with a temporary file).

If there are errors, `init`/`update` ask for confirmation before saving (without an interactive terminal, they fail).

## File safety

aictl saves every file it writes (with hash) in `~/.config/aictl/manifest.json`. During `sync`:

- It only overwrites files that **it created** and that **were not edited manually**.
- An existing unmanaged file (e.g. your `~/.codex/agents/reviewer.toml`) or a manually edited file is marked
  as a **conflict** and is not touched. `--force` overwrites it.
- If you remove an agent/skill from the vault, its managed copy is removed (including empty folders).
- `aictl update --remove X --clean` removes only managed files for that AI.

## Development

```bash
uv venv && uv pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check src tests
```
