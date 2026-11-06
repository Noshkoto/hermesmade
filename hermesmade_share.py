"""hermesmade bot sharing — the one library behind /sharebot, `hermes hermesmade`,
and the desktop plugin's backend.

A shared bot is a Hermes *profile distribution* (distribution.yaml + SOUL.md +
config.yaml + the author's own skills + cron definitions) packed as .tar.gz.

Share path (pack): builds the package from an allow-list, never from "the
profile minus a deny-list". Secrets are removed structurally (config keys
whose name says credential, MCP env/headers, messaging platform blocks) and
then the whole package is pattern-scanned; any hit aborts the share.

Add path (install): downloads from hermesmade.lol, verifies sha256, extracts
with Hermes' own safe extractor, scans every skill with Hermes' skills guard,
then installs through Hermes' own distribution installer, which keeps
credential stores out and merges cron jobs PAUSED. MCP servers arrive
disabled. The model block is seeded from the installer's active profile so
the bot runs on the user's own model and login.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Optional

SITE = os.environ.get("HERMESMADE_URL", "https://hermesmade.lol").rstrip("/")
META_FILE = "hermesmade-bot.json"
USER_AGENT = "hermesmade-plugin/1.2.3"
MAX_DOWNLOAD = 2_000_000
MAX_PACKAGE = 1_500_000
MAX_SKILL_BYTES = 400_000  # a single own-skill dir bigger than this is listed, not shipped

# ------------------------------------------------------------------ helpers --

class ShareError(Exception):
    pass


def _hermes_root() -> Path:
    from hermes_constants import get_default_hermes_root
    return Path(get_default_hermes_root())


def _state_path() -> Path:
    p = _hermes_root() / "hermesmade"
    p.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(p, 0o700)
    except OSError:
        pass
    return p / "shared.json"


def _load_state() -> dict:
    try:
        return json.loads(_state_path().read_text())
    except Exception:
        return {}


def _save_state(data: dict) -> None:
    path = _state_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def profile_dir(name: Optional[str]) -> tuple[str, Path]:
    """(canonical name, dir) for a profile; None/'' = the active one."""
    from hermes_cli import profiles as P
    if not name:
        from hermes_constants import get_hermes_home
        home = Path(get_hermes_home()).resolve()
        for info in P.list_profiles():
            if Path(info.path).resolve() == home:
                return info.name, Path(info.path)
        return "default", home
    for info in P.list_profiles():
        if info.name == name or getattr(info, "display_name", "") == name:
            return info.name, Path(info.path)
    raise ShareError(f"No profile named '{name}'. See `hermes profile list`.")


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    s = re.sub(r"-{2,}", "-", s)[:40].strip("-")
    if len(s) < 3:
        s = (s + "-bot").strip("-")
    return s


def _yaml_load(path: Path) -> dict:
    if not path.is_file():
        return {}
    import hermes_yaml
    try:
        data = hermes_yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _yaml_dump(data: Any) -> str:
    import hermes_yaml
    return hermes_yaml.safe_dump(data, sort_keys=False) or ""


# --------------------------------------------------------- secret handling --

_SECRET_KEYS = {"api_key", "apikey", "key", "token", "access_token", "refresh_token", "id_token",
                "secret", "client_secret", "password", "passwd", "authorization", "private_key",
                "bearer", "jwt", "cookie", "session", "webhook", "webhook_url"}
_SECRET_SUFFIXES = ("_api_key", "_token", "_secret", "_password", "_key", "_access_key", "_cookie",
                    "_webhook", "_webhook_url")
_PLACEHOLDER = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")

# Top-level config keys that are machine, channel, or account wiring, not the
# bot's behaviour. They never ship.
_DROP_TOP = {
    "providers", "custom_providers", "fallback_providers", "credential_pool_strategies", "auxiliary",
    "platforms", "gateway", "discord", "telegram", "slack", "matrix", "mattermost", "whatsapp",
    "signal", "email", "sms", "teams", "wecom", "feishu", "dingtalk", "ntfy", "weixin", "line",
    "DISCORD_HOME_CHANNEL", "TELEGRAM_HOME_CHANNEL", "group_sessions_per_user", "dashboard", "proxy",
    "network", "secrets", "security", "memory", "honcho", "mem0", "telemetry", "updates", "onboarding",
    "plugins", "terminal", "browser", "computer_use", "voice", "stt", "tts", "wake_word", "lsp",
    "checkpoints", "logging", "sessions", "session_reset", "model_catalog", "openrouter", "bedrock",
    "kanban", "cron", "hooks_auto_accept", "command_allowlist", "quick_commands", "approvals",
    "privacy", "delegation", "image_gen", "video_gen", "x_search", "web", "curator", "moa",
    "smart_model_routing", "prefill_messages_file", "known_builtin_toolsets", "known_plugin_toolsets",
    "_left_core_installed", "_left_core_scoped", "mcp_servers",
}
# Keys we DO carry: what makes the bot behave like itself.
_KEEP_TOP = {"agent", "display", "toolsets", "platform_toolsets", "skills", "goals", "compression",
             "context", "tool_output", "tools", "tool_loop_guardrails", "streaming", "human_delay",
             "code_execution", "timezone", "_config_version", "model"}

_SECRET_PATTERNS = [
    (re.compile(r"\bsk-(?:ant-|or-|proj-)?[A-Za-z0-9_-]{20,}"), "API key"),
    (re.compile(r"\bcfat_[A-Za-z0-9]{30,}"), "Cloudflare token"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}"), "GitHub token"),
    (re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{20,}"), "Slack token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS key"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "Google API key"),
    (re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}"), "Stripe live key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
    (re.compile(r"\b[MN][A-Za-z\d_-]{23,25}\.[A-Za-z\d_-]{6}\.[A-Za-z\d_-]{27,}"), "Discord bot token"),
    (re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{33}\b"), "Telegram bot token"),
    (re.compile(r"\bxai-[A-Za-z0-9]{40,}"), "xAI key"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"), "JWT"),
]


def _is_secret_key(k: str) -> bool:
    leaf = str(k).lower().replace("-", "_")
    return leaf in _SECRET_KEYS or leaf.endswith(_SECRET_SUFFIXES)


def _scrub(value: Any, depth: int = 0) -> Any:
    """Drop credential-named keys entirely (not masked: a mask still ships a prefix)."""
    if depth > 20:
        return None
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if _is_secret_key(k) and not (isinstance(v, str) and _PLACEHOLDER.match(v)) and not isinstance(v, (dict, list, bool)):
                continue
            out[k] = _scrub(v, depth + 1)
        return out
    if isinstance(value, list):
        return [_scrub(v, depth + 1) for v in value]
    return value


def scan_text_for_secrets(text: str) -> Optional[str]:
    for rx, label in _SECRET_PATTERNS:
        if rx.search(text):
            return label
    return None


def _env_values(profile: Path) -> list[str]:
    """Literal secret VALUES this profile can use, read through Hermes's own secret scope (the
    profile's secrets plus the process environment Hermes loaded). Used only to catch a key pasted
    into SOUL.md or a skill; values are compared in memory, never stored, logged or sent."""
    vals = set()
    try:
        from agent.secret_scope import build_profile_secret_scope
        vals.update(build_profile_secret_scope(profile).values())
        if profile.resolve() != _hermes_root().resolve():
            vals.update(build_profile_secret_scope(_hermes_root()).values())
    except Exception:
        pass
    return [v for v in vals if isinstance(v, str) and len(v) >= 12 and " " not in v
            and not v.lower().startswith(("http://", "https://", "/", "~"))]


# ------------------------------------------------------------ skill picking --

def _own_skills(profile: Path) -> tuple[list[Path], list[str], list[str]]:
    """(own skill dirs to ship, hub identifiers to ask for, oversized own skills listed only).
    Bundled skills are skipped: every Hermes install already has them."""
    skills = profile / "skills"
    if not skills.is_dir():
        return [], [], []
    bundled = set()
    bm = skills / ".bundled_manifest"
    if bm.is_file():
        bundled = {ln.split(":", 1)[0].strip() for ln in bm.read_text().splitlines() if ln.strip()}
    hub_ids, hub_names = [], set()
    lock = skills / ".hub" / "lock.json"
    if lock.is_file():
        try:
            installed = json.loads(lock.read_text()).get("installed", {})
            for name, rec in installed.items():
                hub_names.add(name)
                ident = (rec or {}).get("identifier") or ""
                if ident and (rec or {}).get("trust_level") != "builtin":
                    hub_ids.append(ident)
        except Exception:
            pass
    disabled = set()
    try:
        cfg = _yaml_load(profile / "config.yaml")
        disabled = set(((cfg.get("skills") or {}).get("disabled")) or [])
    except Exception:
        pass
    own, too_big = [], []
    for md in sorted(skills.rglob("SKILL.md")):
        d = md.parent
        rel = d.relative_to(skills)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if d.name in bundled or d.name in hub_names or d.name in disabled:
            continue
        if any(p.is_symlink() for p in [d, *d.rglob("*")]):
            too_big.append(d.name)
            continue
        size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        if size > MAX_SKILL_BYTES:
            too_big.append(d.name)
            continue
        own.append(d)
    return own, sorted(set(hub_ids)), too_big


_SKIP_IN_SKILL = re.compile(r"(^|/)(\.git|__pycache__|node_modules|\.venv|venv|\.env[^/]*|.*\.pyc|\.DS_Store)(/|$)")


# --------------------------------------------------------------------- pack --

def pack(profile_name: Optional[str] = None, *, title: str = "", tagline: str = "", description: str = "",
         include_skills: Optional[list[str]] = None, include_cron: bool = True, out_dir: Optional[Path] = None
         ) -> dict:
    """Build the share package. Returns a plan dict (paths, manifest, warnings);
    nothing leaves the machine here."""
    pname, pdir = profile_dir(profile_name)
    soul = (pdir / "SOUL.md").read_text(encoding="utf-8", errors="replace") if (pdir / "SOUL.md").is_file() else ""
    if len(soul.strip()) < 20:
        raise ShareError(f"Profile '{pname}' has no real SOUL.md yet. Give the bot a personality before sharing.")

    meta_file = _yaml_load(pdir / "profile.yaml")
    ui = ((meta_file.get("ui_meta") or {}).get("hermes-bots") or {}) if isinstance(meta_file.get("ui_meta"), dict) else {}
    nice = title or ui.get("title") or meta_file.get("display_name") or pname
    if pname == "default" and nice == "default":
        raise ShareError("Your main bot has no name yet. Give it a title, e.g. "
                         "/sharebot --title \"Research Buddy\" (or set one in the desktop bot settings).")
    bot_name = _slug(nice if pname == "default" else pname)
    if bot_name == "default":
        raise ShareError("'default' can't be a shared bot name. Pick a title for it.")
    warnings: list[str] = []

    cfg_path = pdir / "config.yaml"
    cfg_raw = _yaml_load(cfg_path)
    if cfg_path.is_file() and not cfg_raw and cfg_path.read_text(encoding="utf-8", errors="replace").strip():
        raise ShareError(f"{cfg_path} could not be parsed, so its contents cannot be checked for secrets. "
                         "Fix the YAML (run `hermes config check`), then share again.")
    cfg = {k: copy.deepcopy(v) for k, v in cfg_raw.items() if k in _KEEP_TOP and k not in _DROP_TOP}
    model_hint = ""
    if isinstance(cfg.get("model"), dict):
        m = cfg["model"]
        model_hint = str(m.get("default") or "")
        # The installer seeds its own model block; the author's is a hint only.
        cfg.pop("model", None)
    agent = cfg.get("agent")
    if isinstance(agent, dict):
        for k in ("environment_hint", "coding_context"):  # machine-specific prose
            agent.pop(k, None)
    cfg = _scrub(cfg)

    # MCP: names, transport, command/url, args. Never env, headers or auth.
    mcp_meta, mcp_cfg = [], {}
    for name, sc in (cfg_raw.get("mcp_servers") or {}).items():
        if not isinstance(sc, dict):
            continue
        entry = {}
        if sc.get("url"):
            url = str(sc["url"])
            if re.search(r"[?&](key|token|api_key|apikey|auth|secret)=", url, re.I) or "@" in url.split("//", 1)[-1].split("/", 1)[0]:
                warnings.append(f"MCP '{name}' URL carries a credential; shipped without the URL.")
            else:
                entry["url"] = url
        if sc.get("command"):
            entry["command"] = str(sc["command"])
            entry["args"] = [str(a) for a in (sc.get("args") or []) if not scan_text_for_secrets(str(a))]
        env_names = sorted((sc.get("env") or {}).keys()) if isinstance(sc.get("env"), dict) else []
        if env_names:
            entry["env"] = {k: "${" + re.sub(r"[^A-Z0-9_]", "_", k.upper()) + "}" for k in env_names}
        if not entry:
            continue
        entry["enabled"] = False
        mcp_cfg[name] = entry
        mcp_meta.append({"name": name, "transport": "http" if "url" in entry else "stdio", "env": env_names})
    if mcp_cfg:
        cfg["mcp_servers"] = mcp_cfg

    own, hub_ids, too_big = _own_skills(pdir)
    if include_skills is not None:
        keep = set(include_skills)
        own = [d for d in own if d.name in keep]
    for name in too_big:
        warnings.append(f"Skill '{name}' is too large or has symlinks; listed but not shipped.")

    cron_jobs = []
    jobs_file = pdir / "cron" / "jobs.json"
    if include_cron and jobs_file.is_file():
        try:
            raw = json.loads(jobs_file.read_text())
            for j in (raw.get("jobs", []) if isinstance(raw, dict) else raw):
                if not isinstance(j, dict) or not j.get("prompt") or j.get("no_agent") or j.get("script") or j.get("monitor_script"):
                    if isinstance(j, dict) and (j.get("script") or j.get("monitor_script") or j.get("no_agent")):
                        warnings.append(f"Cron job '{j.get('name') or j.get('id')}' runs a local script; not shipped.")
                    continue
                cron_jobs.append({
                    "id": j.get("id") or uuid.uuid4().hex[:12], "name": j.get("name") or "job",
                    "prompt": j["prompt"], "schedule": j.get("schedule"),
                    "schedule_display": j.get("schedule_display"), "skills": j.get("skills") or [],
                    "enabled_toolsets": j.get("enabled_toolsets"), "deliver": "local",
                    "enabled": False, "state": "paused",
                    "paused_reason": "Installed from hermesmade.lol; review it, then resume.",
                })
        except Exception:
            warnings.append("cron/jobs.json was unreadable; schedules not shipped.")

    # env the bot needs: MCP env names + skill-declared required env.
    env_req = {}
    for m in mcp_meta:
        for e in m["env"]:
            env_req[e] = {"name": e, "description": f"for MCP server {m['name']}", "required": False}
    for d in own:
        fm = (d / "SKILL.md").read_text(encoding="utf-8", errors="replace")[:3000]
        for e in re.findall(r"\b([A-Z][A-Z0-9_]{3,}_(?:API_KEY|TOKEN|KEY|SECRET))\b", fm):
            env_req.setdefault(e, {"name": e, "description": f"used by skill {d.name}", "required": False})

    from hermes_cli.version_info import get_version_info
    base = get_version_info().base_version
    major_minor = ".".join(base.split(".")[:2]) + ".0"
    version = str(ui.get("share_version") or "1.0.0")
    st = _load_state().get(bot_name) or {}
    if st.get("version"):
        parts = [int(x) if x.isdigit() else 0 for x in str(st["version"]).split(".")[:3]] + [0, 0, 0]
        version = f"{parts[0]}.{parts[1]}.{parts[2] + 1}"

    manifest = {"name": bot_name, "version": version, "description": tagline or description[:200],
                "hermes_requires": f">={major_minor}", "author": "", "license": "",
                "env_requires": list(env_req.values())}
    meta = {"title": nice, "tagline": tagline, "description": description, "version": version,
            "model_hint": model_hint, "mcp": mcp_meta, "env_requires": list(env_req.values()),
            "hub_skills": hub_ids, "toolsets": sorted((cfg_raw.get("platform_toolsets") or {}).get("cli", []) or [])
            if isinstance(cfg_raw.get("platform_toolsets"), dict) else []}

    work = Path(out_dir or tempfile.mkdtemp(prefix="hermesmade_pack_"))
    root = work / bot_name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    (root / "SOUL.md").write_text(soul, encoding="utf-8")
    (root / "config.yaml").write_text(_yaml_dump(cfg) if cfg else "{}\n", encoding="utf-8")
    (root / "distribution.yaml").write_text(_yaml_dump(manifest), encoding="utf-8")
    (root / META_FILE).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if cron_jobs:
        (root / "cron").mkdir()
        (root / "cron" / "jobs.json").write_text(json.dumps({"jobs": cron_jobs}, indent=2), encoding="utf-8")
    shipped_skills = []
    for d in own:
        rel = d.relative_to(pdir / "skills")
        for f in d.rglob("*"):
            r = f.relative_to(d).as_posix()
            if not f.is_file() or _SKIP_IN_SKILL.search("/" + r):
                continue
            dest = root / "skills" / rel / r
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, dest)
        shipped_skills.append(d.name)

    # Final gate: pattern scan + literal .env values, over every file.
    literals = _env_values(pdir)
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = f.relative_to(root).as_posix()
        hit = scan_text_for_secrets(text)
        if hit:
            raise ShareError(f"Found what looks like a {hit} in {rel}. Remove it, then share again. Nothing was uploaded.")
        if any(v in text for v in literals):
            raise ShareError(f"{rel} contains one of your secret values verbatim. Remove it, then share again. Nothing was uploaded.")

    archive = work / f"{bot_name}-{version}.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for f in sorted(root.rglob("*")):
            info = tf.gettarinfo(str(f), arcname=f.relative_to(work).as_posix())
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = int(time.time())
            if f.is_file():
                info.mode = 0o644
                with open(f, "rb") as fh:
                    tf.addfile(info, fh)
            elif f.is_dir():
                info.mode = 0o755
                tf.addfile(info)
    size = archive.stat().st_size
    if size > MAX_PACKAGE:
        raise ShareError(f"Package is {size // 1024} KB; the limit is {MAX_PACKAGE // 1024} KB. "
                         "Share fewer skills with --skills a,b,c.")
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    return {"profile": pname, "name": bot_name, "title": nice, "version": version, "archive": str(archive),
            "bytes": size, "files": files, "skills": shipped_skills, "hub_skills": hub_ids, "cron": [
                {"name": j["name"], "schedule": (j.get("schedule") or {}).get("display") if isinstance(j.get("schedule"), dict) else j.get("schedule_display")}
                for j in cron_jobs], "mcp": mcp_meta, "env_requires": list(env_req.values()),
            "model_hint": model_hint, "warnings": warnings, "update_of": st.get("id")}


# ------------------------------------------------------------------- upload --

def _multipart(fields: dict, file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = "----hermesmade" + uuid.uuid4().hex
    out = io.BytesIO()
    for k, v in fields.items():
        if v is None or v == "":
            continue
        out.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    out.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{file_path.name}\"\r\n"
              "Content-Type: application/gzip\r\n\r\n".encode())
    out.write(file_path.read_bytes())
    out.write(f"\r\n--{boundary}--\r\n".encode())
    return out.getvalue(), f"multipart/form-data; boundary={boundary}"


def _request(method: str, path: str, *, data: Optional[bytes] = None, headers: Optional[dict] = None,
             limit: int = 200_000) -> tuple[int, bytes]:
    req = urllib.request.Request(SITE + path, data=data, method=method,
                                 headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, r.read(limit + 1)
    except urllib.error.HTTPError as e:
        return e.code, e.read(limit + 1)
    except urllib.error.URLError as e:
        raise ShareError(f"Could not reach {SITE}: {e.reason}")


def upload(plan: dict, handle: str) -> dict:
    handle = handle.strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,30}", handle):
        raise ShareError("Your @handle is required (letters, digits, underscore).")
    state = _load_state()
    prev = state.get(plan["name"]) or {}
    fields = {"handle": handle}
    headers = {}
    if prev.get("id") and prev.get("manage_token"):
        fields["bot_id"] = str(prev["id"])
        headers["x-manage-token"] = prev["manage_token"]
    body, ctype = _multipart(fields, "package", Path(plan["archive"]))
    headers["Content-Type"] = ctype
    code, raw = _request("POST", "/api/bots", data=body, headers=headers)
    try:
        res = json.loads(raw or b"{}")
    except Exception:
        res = {}
    if code >= 400 or not res.get("ok"):
        raise ShareError(res.get("error") or f"Upload failed (HTTP {code}).")
    state[plan["name"]] = {"id": res["id"], "manage_token": res.get("manage_token") or prev.get("manage_token"),
                           "version": plan["version"], "handle": handle, "url": res.get("url"),
                           "profile": plan["profile"], "shared_at": int(time.time())}
    _save_state(state)
    return res


# ------------------------------------------------------------------ install --

def fetch_info(bot_id: str) -> dict:
    bot_id = str(bot_id).strip()
    m = re.search(r"/(?:bots|add)/(\d+)", bot_id) or re.search(r"[?&]add=(\d+)", bot_id) or re.fullmatch(r"#?(\d+)(?:-[a-z0-9-]*)?", bot_id)
    if not m:
        raise ShareError("Give a bot id or a hermesmade.lol/bots/... link.")
    code, raw = _request("GET", f"/api/bots/{m.group(1)}")
    try:
        data = json.loads(raw or b"{}")
    except Exception:
        data = {}
    if code != 200 or "bot" not in data:
        raise ShareError(data.get("error") or f"Bot not found (HTTP {code}).")
    return data["bot"]


def _download(bot: dict, dest: Path) -> Path:
    code, raw = _request("GET", f"/api/bots/{bot['id']}/package", limit=MAX_DOWNLOAD)
    if code != 200:
        raise ShareError(f"Download failed (HTTP {code}).")
    if len(raw) > MAX_DOWNLOAD:
        raise ShareError("Package is larger than allowed.")
    digest = hashlib.sha256(raw).hexdigest()
    if bot.get("sha256") and digest != bot["sha256"]:
        raise ShareError("Package checksum does not match the listing. Not installing.")
    path = dest / f"{bot['name']}.tar.gz"
    path.write_bytes(raw)
    return path


def _scan_skills(root: Path) -> list[dict]:
    from tools.skills_guard import scan_skill
    out = []
    skills = root / "skills"
    if not skills.is_dir():
        return out
    for md in skills.rglob("SKILL.md"):
        res = scan_skill(md.parent, source="community")
        out.append({"skill": md.parent.name, "verdict": res.verdict,
                    "findings": [f"{f.severity}: {f.description} ({f.file}:{f.line})" for f in res.findings[:6]]})
    return out


def _clear_failed_install(name: str) -> None:
    """Remove what an earlier failed add left at a deleted name: the distribution installer of
    older plugin versions wrote the payload into profiles/<name> while profiles/.deleted/<name> still
    marked it deleted, so Hermes refused it on every retry. Only a directory that is still marked
    deleted, holds a hermesmade/distribution payload, and has no sessions or memories is touched."""
    from hermes_cli import profiles as P
    d = P.get_profile_dir(name)
    if not d.is_dir() or not P.named_profile_is_deleted(d) or not (d / "distribution.yaml").is_file():
        return
    if any((d / "sessions").glob("*")) or any((d / "memories").glob("*")) or (d / "state.db").exists():
        return
    shutil.rmtree(d)


def _free_name(want: str) -> str:
    """First name with no live profile and no leftover directory. A name the user deleted earlier
    (a tombstone in profiles/.deleted) is free again: create_profile clears it."""
    from hermes_cli import profiles as P

    def taken(n: str) -> bool:
        if P.profile_exists(n):
            return True
        d = P.get_profile_dir(n)
        return d.exists() and not P.named_profile_is_deleted(d)

    for cand in [want] + [f"{want}-{n}"[:42] for n in range(2, 100)]:
        if not taken(cand):
            return cand
    raise ShareError("Could not find a free profile name.")


def preview(bot_ref: str) -> dict:
    """Download + verify + scan, without installing. The desktop confirm screen shows this."""
    bot = fetch_info(bot_ref)
    with tempfile.TemporaryDirectory(prefix="hermesmade_peek_") as tmp:
        tmp = Path(tmp)
        arc = _download(bot, tmp)
        from hermes_cli.archive_safe import safe_extract_targz
        safe_extract_targz(arc, tmp / "x")
        root = tmp / "x" / bot["name"]
        if not (root / "distribution.yaml").is_file():
            raise ShareError("Package is missing distribution.yaml.")
        scans = _scan_skills(root)
        soul = (root / "SOUL.md").read_text(encoding="utf-8", errors="replace")
    return {"bot": bot, "scans": scans, "soul": soul[:4000], "install_as": _free_name(bot["name"]),
            "blocked": any(s["verdict"] == "dangerous" for s in scans)}


def install(bot_ref: str, *, name: Optional[str] = None, allow_caution: bool = True) -> dict:
    from hermes_cli import profile_distribution as D
    from hermes_cli import profiles as P
    from hermes_cli.archive_safe import safe_extract_targz
    bot = fetch_info(bot_ref)
    target = _free_name(P._canon_valid(name or bot["name"]))
    with tempfile.TemporaryDirectory(prefix="hermesmade_add_") as tmp:
        tmp = Path(tmp)
        arc = _download(bot, tmp)
        safe_extract_targz(arc, tmp / "x")
        root = tmp / "x" / bot["name"]
        scans = _scan_skills(root)
        bad = [s for s in scans if s["verdict"] == "dangerous"]
        if bad:
            raise ShareError("Hermes' skill scanner flagged this bot as dangerous: " +
                             "; ".join(f"{s['skill']}: {', '.join(s['findings'][:2])}" for s in bad) + ". Not installed.")
        if not allow_caution and any(s["verdict"] == "caution" for s in scans):
            raise ShareError("Skill scanner raised cautions; re-run with confirmation to install anyway.")
        # Seed the installer's own model so the bot runs on their login.
        cfg = _yaml_load(root / "config.yaml")
        try:
            from hermes_cli.config import read_user_config_raw
            from hermes_cli.profile_model_seed import launch_model_seed
            from hermes_constants import get_hermes_home
            seed = launch_model_seed(read_user_config_raw(Path(get_hermes_home()) / "config.yaml")) or {}
        except Exception:
            seed = {}
        for k, v in seed.items():
            cfg[k] = v
        for sc in (cfg.get("mcp_servers") or {}).values():
            if isinstance(sc, dict):
                sc["enabled"] = False
        (root / "config.yaml").write_text(_yaml_dump(cfg), encoding="utf-8")
        (root / META_FILE).unlink(missing_ok=True)
        # Create the profile through Hermes first (it clears a tombstone left by an earlier delete of
        # the same name, which the distribution installer alone refuses), then lay the bot over it.
        _clear_failed_install(target)
        created = False
        try:
            P.create_profile(name=target, no_alias=True, no_skills=True)
            created = True
            plan = D.install_distribution(str(root), name=target, force=True, create_alias=False)
        except Exception:
            if created:
                try:
                    P.delete_profile(target, yes=True)
                except Exception:
                    pass
            raise
    pdir = Path(plan.target_dir)
    try:  # --no-skills marker: drop it so bundled skills seed below like any new profile
        (pdir / ".no-bundled-skills").unlink(missing_ok=True)
    except OSError:
        pass
    # Bundled skills, then the bot's identity in the desktop roster.
    try:
        P.seed_profile_skills(pdir, quiet=True)
    except Exception:
        pass
    try:
        if not P.check_alias_collision(target):
            P.create_wrapper_script(target)
    except Exception:
        pass
    try:
        import hermes_yaml
        meta = _yaml_load(pdir / "profile.yaml")
        meta.setdefault("description", (bot.get("tagline") or "")[:200])
        ui = meta.setdefault("ui_meta", {}).setdefault("hermes-bots", {})
        ui.setdefault("title", bot.get("title") or target)
        ui.setdefault("description", (bot.get("tagline") or "")[:200])
        ui.setdefault("created", int(time.time() * 1000))
        meta["hermesmade"] = {"id": bot["id"], "version": bot.get("version"), "author": bot.get("owner_handle"),
                              "source": f"{SITE}/bots/{bot.get('slug') or bot['id']}"}
        (pdir / "profile.yaml").write_text(_yaml_dump(meta), encoding="utf-8")
    except Exception:
        pass
    try:
        _request("POST", f"/api/bots/{bot['id']}/installed", data=b"")
    except Exception:
        pass
    m = bot.get("meta") or {}
    return {"ok": True, "profile": target, "path": str(pdir), "title": bot.get("title"),
            "cron_paused": len(m.get("cron") or []), "mcp_disabled": [x.get("name") for x in m.get("mcp") or []],
            "env_requires": m.get("env_requires") or [], "hub_skills": m.get("hub_skills") or [],
            "scans": scans}


def my_shares() -> dict:
    return {k: {kk: vv for kk, vv in v.items() if kk != "manage_token"} for k, v in _load_state().items()}


def unshare(bot_name: str) -> dict:
    st = _load_state()
    rec = st.get(bot_name)
    if not rec:
        raise ShareError(f"You have not shared a bot called '{bot_name}' from this machine.")
    code, raw = _request("POST", f"/api/bots/{rec['id']}/delete", data=b"", headers={"x-manage-token": rec["manage_token"]})
    if code != 200:
        raise ShareError(f"Delete failed (HTTP {code}).")
    st.pop(bot_name)
    _save_state(st)
    return {"ok": True}
