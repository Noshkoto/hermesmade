"""Grok Bot -> Hermes bots, one Hermes bot (profile) per Grok Bot.

Grok Bot keeps everything in its cloud account and has no export button, so each Bot exports
itself: the user pastes the official export prompt into its chat and it replies with one JSON
document. Reading and mapping that document is done by the official ``agent-importers`` plugin
(NousResearch/hermes-official-plugins, MIT); this module only adds what that importer leaves to
the user: a fresh profile per Bot, running on the installer's own model, shown in the desktop bot
list. Nothing here talks to xAI or any network service, and no credential is ever read or written.
The importer is installed from the Hermes catalog only after the user says yes.

Routines arrive paused (the Grok copy keeps running until the user turns it off). Event routines
are written to a notes file to rebuild. Apps with a remote MCP URL come over as MCP servers; other
apps are listed, since their logins stay in Grok Bot.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

PLUGIN = "agent-importers"
_PKG_ALIAS = "_hm_agent_importers"
MAX_TEXT = 2_000_000


class MigrateError(Exception):
    pass


# ----------------------------------------------------------------- importer --
def _plugins_dir() -> Path:
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home()) / "plugins"


def _load_importer():
    """The official importer's ``grok_bot`` module: the copy Hermes already loaded when the plugin is
    enabled, else the installed plugin's files (an installed-but-disabled plugin)."""
    try:
        return importlib.import_module("hermes_plugins.agent_importers.grok_bot")
    except Exception:
        pass
    if f"{_PKG_ALIAS}.grok_bot" in sys.modules:
        return sys.modules[f"{_PKG_ALIAS}.grok_bot"]
    root = _plugins_dir() / PLUGIN
    if not (root / "grok_bot.py").is_file():
        return None
    spec = importlib.util.spec_from_file_location(_PKG_ALIAS, root / "__init__.py",
                                                  submodule_search_locations=[str(root)])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[_PKG_ALIAS] = pkg
    try:
        spec.loader.exec_module(pkg)
        return importlib.import_module(f"{_PKG_ALIAS}.grok_bot")
    except Exception:
        for k in [k for k in sys.modules if k == _PKG_ALIAS or k.startswith(_PKG_ALIAS + ".")]:
            sys.modules.pop(k, None)
        raise


class ImporterMissing(MigrateError):
    """agent-importers is not installed; the caller asks the user before installing it."""


INSTALL_HINT = f"hermes plugins install {PLUGIN}"


def importer_installed() -> bool:
    try:
        return _load_importer() is not None
    except Exception:
        return False


def install_importer() -> None:
    """Install the official importer from the Hermes plugin catalog (its reviewed pin). Only call this
    after the user said yes: the desktop button and the CLI prompt are that yes. Never prompts."""
    if importer_installed():
        return
    cmd = [sys.executable, "-m", "hermes_cli.main", "plugins", "install", PLUGIN, "--enable"]
    try:
        out = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise MigrateError(f"Could not install {PLUGIN}: {e}. Run `{INSTALL_HINT}` yourself.") from e
    if not importer_installed():
        tail = (out.stderr or out.stdout or "").strip().splitlines()[-3:]
        raise MigrateError(f"{PLUGIN} did not install. Run `{INSTALL_HINT}` and try again."
                           + (f" ({' / '.join(tail)})" if tail else ""))


def ensure_importer():
    """The importer module, or ImporterMissing so the caller can ask before installing it."""
    mod = _load_importer()
    if mod is None:
        raise ImporterMissing(f"Moving bots from Grok Bot uses the official {PLUGIN} plugin, which "
                              f"is not installed. Install it with `{INSTALL_HINT}`.")
    return mod


def export_prompt() -> str:
    mod = ensure_importer()
    return mod.EXPORT_PROMPT


# ------------------------------------------------------------------- parse --
def _texts_to_files(texts: list[str], tmp: Path) -> list[Path]:
    files = []
    for i, t in enumerate(texts):
        if not t or not t.strip():
            continue
        if len(t) > MAX_TEXT:
            raise MigrateError("That export is too large (2 MB max per reply).")
        p = tmp / f"grok-bot-export-{i + 1}.txt"
        p.write_text(t, encoding="utf-8")
        files.append(p)
    return files


def _sources(texts: Optional[list[str]], files: Optional[list[str]], tmp: Path, mod) -> list[Path]:
    out = _texts_to_files(list(texts or []), tmp)
    for f in files or []:
        p = Path(f).expanduser()
        if not p.exists():
            raise MigrateError(f"No file at {p}")
        # A file the user chose is read as-is (find_export_files only lists export-named files).
        out.extend([p] if p.is_file() else mod.find_export_files(p))
    return out


def find_downloads() -> list[str]:
    mod = ensure_importer()
    return [str(p) for p in mod.find_export_files(None)]


def _bots(mod, sources: list[Path]) -> list[dict]:
    errors, bots = [], []
    for p in sources:
        try:
            parsed, _ = mod.redact_secrets(mod.parse_export(p.read_text(encoding="utf-8", errors="replace")))
            bots.extend(parsed)
        except mod.ExportFormatError as e:
            errors.append(str(e))
    if not bots:
        raise MigrateError(errors[0] if errors else "No Grok Bot export found. Paste the Bot's whole reply.")
    return mod.merge_bots(bots)


def _summary(mod, bot: dict) -> dict:
    routines = mod._dicts(bot.get("routines"))
    from cron import jobs as cron_jobs
    scheduled = [r for r in routines if mod._routine_schedule(r, cron_jobs.parse_schedule) is not None]
    return {
        "name": str(bot["name"]).strip(),
        "title": str(bot.get("title") or "").strip(),
        "instructions": str(bot.get("instructions") or "").strip()[:1200],
        "skills": [str(s.get("name") or "").strip() for s in mod._dicts(bot.get("skills")) if s.get("name")],
        "routines": [str(r.get("name") or "routine").strip() for r in scheduled],
        "event_routines": [str(r.get("name") or "routine").strip() for r in routines if r not in scheduled],
        "memories": len(mod._strings(bot.get("memories"))),
        "user_facts": len(mod._strings(bot.get("user_facts"))),
        "apps": [str(a.get("name") or "").strip() for a in mod._dicts(bot.get("apps")) if a.get("name")],
    }


def _profile_for(bot_name: str) -> tuple[str, bool]:
    """(profile name, already migrated) for this Grok Bot: reuse the profile an earlier migration
    made for it, else the first free name."""
    from hermes_cli import profiles as P
    import hermes_yaml

    def origin(n: str) -> str:
        try:
            meta = hermes_yaml.safe_load((P.get_profile_dir(n) / "profile.yaml").read_text()) or {}
            return str((meta.get("migrated_from") or {}).get("grok_bot") or "").lower()
        except Exception:
            return ""

    rows = [r.name for r in P.list_profiles()]
    for n in rows:  # any name, so a bot renamed on the first run is found again
        if n != "default" and origin(n) == bot_name.lower():
            return n, True
    taken = set(rows)
    want = P._canon_valid(_slug(bot_name))
    for n in [want] + [f"{want}-{i}" for i in range(2, 100)]:
        if n[:42] not in taken:
            return n[:42], False
    raise MigrateError("Could not find a free bot name.")


_RESERVED_SLUGS = frozenset({"default", "hermes", "test", "tmp", "root", "admin"})


def _slug(s: str) -> str:
    import re
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:40]
    if not s or s in _RESERVED_SLUGS:
        s = f"grok-{s or 'bot'}"
    if not s[0].isalpha():
        s = f"grok-{s}"
    return s


def preview(texts: Optional[list[str]] = None, files: Optional[list[str]] = None) -> dict:
    """What a migration would create, without writing anything."""
    mod = ensure_importer()
    with tempfile.TemporaryDirectory(prefix="hm_grok_") as tmp:
        bots = _bots(mod, _sources(texts, files, Path(tmp), mod))
    out = []
    for b in bots:
        s = _summary(mod, b)
        s["profile"], s["existing"] = _profile_for(s["name"])
        out.append(s)
    return {"bots": out}


# ----------------------------------------------------------------- migrate --
def _new_profile(name: str, bot: dict) -> Path:
    from hermes_cli import profiles as P
    path = P.create_profile(name=name, no_alias=True, description=(str(bot.get("title") or "")[:200] or None))
    # create_profile copies only the active model block (never .env), so the bot runs on the
    # installer's own model and login.
    try:
        P.seed_profile_skills(path, quiet=True)
    except Exception:
        pass
    try:
        if not P.check_alias_collision(name):
            P.create_wrapper_script(name)
    except Exception:
        pass
    return path


def _mark(path: Path, bot: dict) -> None:
    import hermes_yaml
    p = path / "profile.yaml"
    try:
        meta = hermes_yaml.safe_load(p.read_text()) if p.is_file() else {}
    except Exception:
        meta = {}
    meta = meta if isinstance(meta, dict) else {}
    name, title = str(bot["name"]).strip(), str(bot.get("title") or "").strip()
    meta.setdefault("display_name", name)
    if title:
        meta.setdefault("description", title[:200])
    ui = meta.setdefault("ui_meta", {}).setdefault("hermes-bots", {})
    ui.setdefault("title", name)
    if title:
        ui.setdefault("description", title[:200])
    ui.setdefault("created", int(time.time() * 1000))
    meta["migrated_from"] = {"grok_bot": name, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    from utils import atomic_yaml_write
    atomic_yaml_write(p, meta, sort_keys=False)


def migrate(texts: Optional[list[str]] = None, files: Optional[list[str]] = None, *,
            only: Optional[list[str]] = None, names: Optional[dict] = None,
            activate_routines: bool = False) -> dict:
    """Create (or top up) one Hermes bot per exported Grok Bot. ``names`` maps a Grok Bot name to the
    profile name to use for a new bot; ``only`` limits the run to those Bots."""
    mod = ensure_importer()
    names = {k.lower(): v for k, v in (names or {}).items() if v}
    picked = {n.strip().lower() for n in only or [] if n.strip()}
    results = []
    with tempfile.TemporaryDirectory(prefix="hm_grok_") as tmp:
        sources = _sources(texts, files, Path(tmp), mod)
        bots = _bots(mod, sources)
        for bot in bots:
            bname = str(bot["name"]).strip()
            if picked and bname.lower() not in picked:
                continue
            profile, existing = _profile_for(bname)
            if not existing and names.get(bname.lower()):
                from hermes_cli import profiles as P
                profile = P._canon_valid(names[bname.lower()])
                if P.profile_exists(profile):
                    raise MigrateError(f"A bot named {profile!r} already exists. Pick another name for {bname}.")
            from hermes_cli import profiles as P
            path = P.get_profile_dir(profile) if existing else _new_profile(profile, bot)
            importer = mod.GrokBotImporter(sources, path.resolve(), execute=True, overwrite=False,
                                           activate_routines=activate_routines, bot_names=[bname])
            report = importer.run()
            _mark(path, bot)
            items = report.get("items", [])
            jobs = [i.get("details", {}).get("job_id") or i.get("job_id") for i in items
                    if i.get("kind") == "routine" and i.get("status") == "imported"]
            results.append({
                "bot": bname, "profile": profile, "updated": existing, "path": str(path),
                "summary": report.get("summary", {}),
                "routines_paused": sum(1 for i in items if i.get("kind") == "routine"
                                       and i.get("status") == "imported" and i.get("paused", True)),
                "job_ids": [j for j in jobs if j],
                "notes": [i.get("reason") for i in items if i.get("status") in ("error", "conflict")
                          or (i.get("kind") in ("apps", "event-routines", "bots", "routine-check") and i.get("reason"))][:12],
                "stripped_secrets": report.get("stripped_secrets", []),
            })
    if not results:
        raise MigrateError("None of the exported Bots matched your selection.")
    return {"results": results}
