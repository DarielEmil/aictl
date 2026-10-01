"""CLI de aictl: init, update, sync, status, doctor, mapping."""

from __future__ import annotations

import copy
import os
import sys

import questionary
import typer
from rich.console import Console
from rich.table import Table

from aictl import ALL_TARGETS, __version__, checks, config, manifest, mapping, prompts
from aictl import sync as syncer
from aictl import upgrade as upgrader
from aictl.config import (
    DEFAULT_AGENTS_DIR,
    DEFAULT_SKILLS_DIR,
    Config,
    ConfigError,
    SourceConfig,
)
from aictl.mapping import MappingError
from aictl.sources import SourceError, build_source

app = typer.Typer(
    help="Sincroniza agents y skills desde Obsidian hacia tus herramientas de IA.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err = Console(stderr=True)

OP_STYLE = {
    "create": ("creado", "green"),
    "update": ("actualizado", "cyan"),
    "unchanged": ("sin cambios", "dim"),
    "conflict": ("conflicto", "yellow"),
    "delete": ("eliminado", "red"),
    "keep": ("conservado", "yellow"),
}
DRY_LABEL = {"create": "crear", "update": "actualizar", "delete": "eliminar"}


def _fail(message: str) -> None:
    err.print(f"[red]Error:[/red] {message}")
    raise typer.Exit(1)


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _parse_targets(value: str) -> list[str]:
    names = [t.strip().lower() for t in value.split(",") if t.strip()]
    unknown = [n for n in names if n not in ALL_TARGETS]
    if unknown:
        _fail(f"AIs desconocidas: {', '.join(unknown)}. Opciones: {', '.join(ALL_TARGETS)}")
    return list(dict.fromkeys(names))


def _detected(maps: mapping.Mapping) -> set[str]:
    return {n for n in ALL_TARGETS if n in maps.targets and maps.targets[n].root.is_dir()}


def _load_config() -> Config:
    try:
        return config.load()
    except ConfigError as exc:
        _fail(str(exc))


def _load_mapping(cfg: Config | None) -> mapping.Mapping:
    try:
        return mapping.load(cfg)
    except MappingError as exc:
        _fail(str(exc))


def _short(path) -> str:
    """Ruta con ~ en lugar del HOME, para tablas más legibles."""
    text = str(path)
    home = os.path.expanduser("~")
    return "~" + text[len(home):] if text.startswith(home + os.sep) else text


def _print_summary(cfg: Config, maps: mapping.Mapping) -> None:
    console.print(f"[bold]Vault:[/bold]  {cfg.source.vault}")
    console.print(f"[bold]Agents:[/bold] {cfg.source.agents_path}")
    console.print(f"[bold]Skills:[/bold] {cfg.source.skills_path}")
    console.print("[bold]Archivos que se modificarán:[/bold]")
    for name in cfg.targets:
        console.print(f"  [cyan]{name}[/cyan]")
        for line in maps.get(name).describe():
            console.print(f"    → {_short(line)}")


def _print_actions(actions: list[syncer.Action], dry_run: bool, verbose: bool) -> None:
    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("AI")
    table.add_column("Acción")
    table.add_column("Archivo", overflow="fold")
    for a in actions:
        if a.op == "unchanged" and not verbose:
            continue
        label, style = OP_STYLE[a.op]
        if dry_run and a.op in DRY_LABEL:
            label = DRY_LABEL[a.op]
        note = f" [dim]({a.reason})[/dim]" if a.reason else ""
        table.add_row(a.target, f"[{style}]{label}[/{style}]", f"{_short(a.path)}{note}")
    if table.row_count:
        console.print(table)

    counts: dict[str, int] = {}
    for a in actions:
        counts[a.op] = counts.get(a.op, 0) + 1
    parts = [f"{OP_STYLE[op][0]}: {n}" for op, n in counts.items()]
    prefix = "[bold]Dry-run[/bold] (no se escribió nada): " if dry_run else ""
    console.print(prefix + (", ".join(parts) if parts else "nada que hacer"))
    if counts.get("conflict"):
        console.print(
            "[yellow]Hay conflictos: esos archivos no los gestiona aictl o fueron editados a mano. "
            "Usa `aictl sync --force` para sobrescribirlos.[/yellow]"
        )


CHECK_ICON = {"ok": "[green]✓[/green]", "warn": "[yellow]![/yellow]", "error": "[red]✗[/red]"}


def _print_report(report: checks.Report) -> None:
    for c in report.checks:
        console.print(f"  {CHECK_ICON[c.level]} {c.message}")


def _verify_before_save(report: checks.Report, interactive: bool) -> None:
    """Muestra las comprobaciones y, si hay errores, pide confirmación (o falla sin TTY)."""
    console.print("[bold]Comprobando acceso…[/bold]")
    _print_report(report)
    if not report.has_errors:
        return
    if not interactive:
        _fail("Hay errores de acceso; corrígelos antes de guardar la configuración.")
    if not prompts.confirm("Hay errores de acceso. ¿Guardar la configuración de todos modos?", default=False):
        raise typer.Abort()


def _run_sync(
    cfg: Config,
    only: list[str] | None = None,
    dry_run: bool = False,
    force: bool = False,
    verbose: bool = False,
) -> None:
    maps = _load_mapping(cfg)
    targets = only or cfg.targets
    if not targets:
        _fail("No hay AIs seleccionadas. Usa `aictl update` para elegirlas.")
    try:
        for name in targets:
            maps.get(name)
        items = build_source(cfg).items()
        outputs = syncer.build_outputs(items, maps, targets)
    except (SourceError, MappingError, syncer.SyncError) as exc:
        _fail(str(exc))
    except OSError as exc:
        _fail(f"No se pudo leer {exc.filename}: {exc.strerror}")

    agents = sum(1 for i in items if i.kind == "agent")
    console.print(f"Leídos [bold]{agents}[/bold] agents y [bold]{len(items) - agents}[/bold] skills")
    state = manifest.load()
    actions = syncer.plan(outputs, state, targets, force=force)
    _print_actions(actions, dry_run, verbose)
    if dry_run:
        return
    roots = {n: maps.get(n).root for n in targets}
    syncer.execute(actions, state, roots)
    state.touch()
    manifest.save(state)


def _remove_target_files(name: str, maps: mapping.Mapping, force: bool = False) -> None:
    state = manifest.load()
    actions = syncer.plan_removal(name, state, force=force)
    if not actions:
        return
    root = maps.targets[name].root if name in maps.targets else None
    syncer.execute(actions, state, {name: root} if root else {})
    manifest.save(state)
    _print_actions(actions, dry_run=False, verbose=False)



def _version(value: bool) -> None:
    if value:
        console.print(f"aictl {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version, is_eager=True, help="Muestra la versión."
    ),
) -> None:
    pass


@app.command()
def init(
    vault: str | None = typer.Option(None, help="Ruta del vault de Obsidian."),
    agents_dir: str | None = typer.Option(None, help="Carpeta de agents dentro del vault."),
    skills_dir: str | None = typer.Option(None, help="Carpeta de skills dentro del vault."),
    targets: str | None = typer.Option(
        None, help=f"AIs separadas por coma: {','.join(ALL_TARGETS)}."
    ),
    force: bool = typer.Option(False, "--force", help="Sobrescribe una configuración existente."),
    sync: bool | None = typer.Option(None, "--sync/--no-sync", help="Ejecuta sync al terminar."),
) -> None:
    """Inicializa aictl: ruta del vault, carpetas de agents/skills y AIs a configurar."""
    if config.exists() and not force:
        _fail(
            f"Ya existe una configuración en {config.config_path()}. "
            "Usa `aictl update` para modificarla o `aictl init --force` para empezar de cero."
        )
    maps = _load_mapping(None)
    interactive = _interactive()
    if not interactive and not (vault and targets):
        _fail("Sin terminal interactiva hay que pasar al menos --vault y --targets.")

    vault = vault or prompts.vault()
    agents_dir = agents_dir or (
        prompts.folder(vault, "agents", DEFAULT_AGENTS_DIR) if interactive else DEFAULT_AGENTS_DIR
    )
    skills_dir = skills_dir or (
        prompts.folder(vault, "skills", DEFAULT_SKILLS_DIR) if interactive else DEFAULT_SKILLS_DIR
    )
    selected = _parse_targets(targets) if targets else prompts.targets([], _detected(maps))

    cfg = Config(
        source=SourceConfig(vault_path=vault, agents_dir=agents_dir, skills_dir=skills_dir),
        targets=selected,
    )
    _print_summary(cfg, maps)
    report = checks.check_source(cfg).extend(checks.check_targets(maps, cfg.targets))
    _verify_before_save(report, interactive)
    path = config.save(cfg)
    console.print(f"[green]Configuración guardada en {path}[/green]")

    if sync is None:
        sync = (
            interactive
            and not report.has_errors
            and prompts.confirm("¿Ejecutar `aictl sync` ahora?")
        )
    if sync:
        _run_sync(cfg)


@app.command()
def update(
    vault: str | None = typer.Option(None, help="Nueva ruta del vault de Obsidian."),
    agents_dir: str | None = typer.Option(None, help="Nueva carpeta de agents."),
    skills_dir: str | None = typer.Option(None, help="Nueva carpeta de skills."),
    add: str | None = typer.Option(None, help="AIs a añadir, separadas por coma."),
    remove: str | None = typer.Option(None, help="AIs a quitar, separadas por coma."),
    clean: bool | None = typer.Option(
        None,
        "--clean/--no-clean",
        help="Al quitar una AI, borra (o conserva) los archivos que aictl creó para ella.",
    ),
) -> None:
    """Modifica TU CONFIGURACIÓN: ruta del vault, carpetas y AIs seleccionadas.

    Para actualizar la herramienta aictl en sí, usa `aictl upgrade`.
    """
    old = _load_config()
    cfg = copy.deepcopy(old)
    maps = _load_mapping(cfg)
    by_flags = any(v is not None for v in (vault, agents_dir, skills_dir, add, remove))

    if by_flags:
        if vault:
            cfg.source.vault_path = vault
        if agents_dir:
            cfg.source.agents_dir = agents_dir
        if skills_dir:
            cfg.source.skills_dir = skills_dir
        if add:
            cfg.targets += [t for t in _parse_targets(add) if t not in cfg.targets]
        if remove:
            drop = set(_parse_targets(remove))
            cfg.targets = [t for t in cfg.targets if t not in drop]
    elif _interactive():
        if not _edit_interactively(cfg, maps):
            console.print("Sin cambios.")
            return
    else:
        _fail("Sin terminal interactiva usa flags: --vault, --agents-dir, --skills-dir, --add, --remove.")

    if cfg.to_dict() == old.to_dict():
        console.print("Sin cambios.")
        return

    _print_diff(old, cfg)
    added = [t for t in cfg.targets if t not in old.targets]
    report = checks.Report()
    if old.source != cfg.source:
        report.extend(checks.check_source(cfg))
    report.extend(checks.check_targets(maps, added))
    if report.checks:
        _verify_before_save(report, interactive=not by_flags)
    if not by_flags and not report.has_errors and not prompts.confirm("¿Guardar los cambios?"):
        raise typer.Abort()
    config.save(cfg)
    console.print(f"[green]Configuración guardada en {config.config_path()}[/green]")

    removed = [t for t in old.targets if t not in cfg.targets]
    managed = manifest.load().targets()
    for name in removed:
        if name not in managed:
            continue
        do_clean = clean
        if do_clean is None:
            do_clean = _interactive() and prompts.confirm(
                f"¿Borrar los archivos que aictl creó para {name}?", default=False
            )
        if do_clean:
            _remove_target_files(name, maps)

    if added or old.source != cfg.source:
        console.print("Ejecuta [bold]aictl sync[/bold] para aplicar los cambios.")


def _edit_interactively(cfg: Config, maps: mapping.Mapping) -> bool:
    """Menú de edición. Devuelve False si el usuario sale sin guardar."""
    while True:
        choice = prompts.select(
            "¿Qué quieres modificar?",
            [
                questionary.Choice(f"Ruta del vault       ({cfg.source.vault_path})", "vault"),
                questionary.Choice(
                    f"Carpetas del vault   (agents: {cfg.source.agents_dir}, "
                    f"skills: {cfg.source.skills_dir})",
                    "folders",
                ),
                questionary.Choice(f"AIs seleccionadas    ({', '.join(cfg.targets) or '-'})", "targets"),
                questionary.Choice("Guardar y salir", "save"),
                questionary.Choice("Salir sin guardar", "quit"),
            ],
        )
        if choice == "vault":
            cfg.source.vault_path = prompts.vault(cfg.source.vault_path)
        elif choice == "folders":
            cfg.source.agents_dir = prompts.folder(
                cfg.source.vault_path, "agents", cfg.source.agents_dir
            )
            cfg.source.skills_dir = prompts.folder(
                cfg.source.vault_path, "skills", cfg.source.skills_dir
            )
        elif choice == "targets":
            cfg.targets = prompts.targets(cfg.targets, _detected(maps))
        else:
            return choice == "save"


def _print_diff(old: Config, new: Config) -> None:
    console.print("[bold]Cambios:[/bold]")
    for key in ("vault_path", "agents_dir", "skills_dir"):
        before, after = getattr(old.source, key), getattr(new.source, key)
        if before != after:
            console.print(f"  {key}: [red]{before}[/red] → [green]{after}[/green]")
    for name in new.targets:
        if name not in old.targets:
            console.print(f"  [green]+ {name}[/green]")
    for name in old.targets:
        if name not in new.targets:
            console.print(f"  [red]- {name}[/red]")


@app.command()
def sync(
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Muestra qué haría sin escribir."),
    target: str | None = typer.Option(
        None, "--target", "-t", help="Sincroniza solo estas AIs (separadas por coma)."
    ),
    force: bool = typer.Option(
        False, "--force", help="Sobrescribe también archivos no gestionados o editados a mano."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Muestra también los sin cambios."),
) -> None:
    """Sincroniza los agents y skills de Obsidian hacia las AIs seleccionadas."""
    cfg = _load_config()
    only = None
    if target:
        only = _parse_targets(target)
        missing = [t for t in only if t not in cfg.targets]
        if missing:
            _fail(f"{', '.join(missing)} no está seleccionada. Añádela con `aictl update --add`.")
    _run_sync(cfg, only, dry_run=dry_run, force=force, verbose=verbose)


@app.command()
def status() -> None:
    """Muestra la configuración actual y el estado del último sync."""
    cfg = _load_config()
    maps = _load_mapping(cfg)
    _print_summary(cfg, maps)
    state = manifest.load()
    console.print(f"[bold]Mapeo:[/bold]  {maps.source}")
    console.print(f"[bold]Último sync:[/bold] {state.last_sync or 'nunca'}")
    for name in cfg.targets:
        console.print(f"  {name}: {len(state.paths_for(name))} archivos gestionados")


@app.command()
def doctor() -> None:
    """Verifica el vault, el mapeo y los permisos de las carpetas destino."""
    ok = True

    def check(cond: bool, good: str, bad: str) -> None:
        nonlocal ok
        ok &= cond
        console.print(f"  [green]✓[/green] {good}" if cond else f"  [red]✗[/red] {bad}")

    console.print(f"[bold]aictl {__version__}[/bold]")
    check(config.exists(), f"config: {config.config_path()}", "no hay configuración (`aictl init`)")
    if not config.exists():
        raise typer.Exit(1)
    cfg = _load_config()
    try:
        maps = mapping.load(cfg)
        check(True, f"mapeo válido ({maps.source})", "")
    except MappingError as exc:
        check(False, "", str(exc))
        raise typer.Exit(1)

    console.print("[bold]Lectura del vault[/bold]")
    source_report = checks.check_source(cfg)
    _print_report(source_report)
    console.print("[bold]Escritura en las AIs[/bold]")
    targets_report = checks.check_targets(maps, cfg.targets)
    _print_report(targets_report)
    ok = ok and not source_report.has_errors and not targets_report.has_errors
    raise typer.Exit(0 if ok else 1)


@app.command()
def upgrade(
    no_pull: bool = typer.Option(
        False, "--no-pull", help="No hace git pull; solo reinstala el código local del repo."
    ),
    check: bool = typer.Option(
        False, "--check", help="Solo comprueba si hay actualizaciones, sin instalar nada."
    ),
) -> None:
    """Actualiza la herramienta aictl (git pull + reinstalación). No toca tu configuración."""
    try:
        info = upgrader.load_install_info()
    except upgrader.UpgradeError as exc:
        _fail(str(exc))
    source = info.source_dir
    console.print(f"[bold]Repo de origen:[/bold] {_short(source)}  ([dim]{info.method}[/dim])")

    before = upgrader.current_commit(source) if upgrader.is_git_repo(source) else None
    remote = upgrader.upstream(source) if before else None

    if check:
        if not remote:
            console.print("El repo no tiene una rama remota configurada; no hay de dónde comprobar.")
            return
        try:
            pending = upgrader.pending_commits(source)
        except upgrader.UpgradeError as exc:
            _fail(str(exc))
        if pending:
            console.print(f"Hay [bold]{len(pending)}[/bold] cambios nuevos en {remote}:")
            for line in pending:
                console.print(f"  {line}")
            console.print("Ejecuta [bold]aictl upgrade[/bold] para instalarlos.")
        else:
            console.print(f"[green]aictl está al día con {remote}.[/green]")
        return

    try:
        if no_pull:
            console.print("Sin git pull: se reinstala el código local.")
        elif not before:
            console.print("[yellow]El repo no es git o no tiene commits; se reinstala el código local.[/yellow]")
        elif not remote:
            console.print(
                "[yellow]La rama no tiene remoto (upstream); se reinstala el código local.[/yellow]"
            )
        else:
            if upgrader.has_local_changes(source):
                console.print(
                    "[yellow]Aviso: el repo tiene cambios locales sin commit; "
                    "git solo actualizará si no hay conflicto.[/yellow]"
                )
            console.print(f"Trayendo cambios de [bold]{remote}[/bold]…")
            upgrader.pull(source)
            after = upgrader.current_commit(source)
            if after == before:
                console.print("No había cambios nuevos en el remoto.")
            else:
                console.print(f"Actualizado {before} → {after}:")
                for line in upgrader.changelog(source, before, after):
                    console.print(f"  {line}")

        console.print("Reinstalando aictl…")
        upgrader.reinstall(info)
    except upgrader.UpgradeError as exc:
        _fail(str(exc))
    console.print(
        f"[green]aictl actualizado.[/green] Tu configuración en "
        f"{_short(config.config_dir())} no se ha modificado."
    )


@app.command("mapping")
def mapping_cmd(
    export: bool = typer.Option(
        False, "--export", help="Copia el mapeo por defecto a ~/.config/aictl/targets.yaml."
    ),
) -> None:
    """Muestra el YAML de mapeo en uso o lo exporta para personalizarlo."""
    if export:
        dest = mapping.user_mapping_path()
        if dest.exists():
            _fail(f"Ya existe {dest}; edítalo directamente o bórralo para regenerarlo.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(mapping.default_text(), encoding="utf-8")
        console.print(f"[green]Mapeo exportado a {dest}[/green] (tiene prioridad sobre el de serie)")
        return
    cfg = config.load() if config.exists() else None
    path = mapping.resolve_path(cfg)
    console.print(f"[dim]# {path or 'mapeo por defecto (incluido en aictl)'}[/dim]")
    console.print(path.read_text(encoding="utf-8") if path else mapping.default_text(), markup=False)

