"""hermesmade — share Hermes bots to hermesmade.lol and add bots from it.

Surfaces (all call hermesmade_share):
  /sharebot [handle]              slash command, any surface (CLI, TUI, desktop, gateway)
  hermes hermesmade share|add|...  CLI
  hermesmade_bots tool             so the agent can do it when asked ("share this bot")
  hermes hermesmade migrate-grok   move Grok Bot bots in (hermesmade_migrate, via agent-importers)
  desktop/plugin.js                Add-bot confirm page opened by hermes://open/hermesmade?add=<id>
  dashboard/plugin_api.py          backend for the desktop page
"""
from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import hermesmade_share as H  # noqa: E402

TOOLSET = "hermesmade"


def _fmt_plan(p: dict) -> str:
    lines = [f"Bot: {p['title']}  (installs as `{p['name']}`, v{p['version']}, {p['bytes'] // 1024 or 1} KB)",
             f"From profile: {p['profile']}",
             "Ships:"]
    lines += [f"  - {f}" for f in p["files"]]
    if p["hub_skills"]:
        lines.append(f"Hub skills it asks installers for: {', '.join(p['hub_skills'][:12])}")
    if p["cron"]:
        lines.append("Schedules (arrive PAUSED): " + ", ".join(f"{j['name']} [{j['schedule']}]" for j in p["cron"]))
    if p["mcp"]:
        lines.append("MCP (arrive OFF, no credentials): " + ", ".join(m["name"] for m in p["mcp"]))
    lines.append("Never ships: .env, auth.json, API keys, bot tokens, memories, sessions, chat history, your model login.")
    for w in p["warnings"]:
        lines.append(f"Note: {w}")
    if p.get("update_of"):
        lines.append(f"This updates your existing listing #{p['update_of']}.")
    return "\n".join(lines)


# ---------------------------------------------------------------- slash ----
_PENDING: dict[str, dict] = {}


def _slash(raw_args: str, **_ctx) -> str:
    """/sharebot              preview the active bot
       /sharebot yes @handle  upload the previewed package
       /sharebot add <id>     install a bot from hermesmade.lol
       /sharebot mine         list what you've shared"""
    try:
        args = shlex.split(raw_args or "")
    except ValueError:
        args = (raw_args or "").split()
    try:
        if args and args[0] == "add":
            if len(args) < 2:
                return "Usage: /sharebot add <bot id or hermesmade.lol link>"
            out = H.install(args[1])
            return _fmt_install(out)
        if args and args[0] == "mine":
            shares = H.my_shares()
            if not shares:
                return "You haven't shared any bots from this machine yet."
            return "\n".join(f"- {k} v{v.get('version')}: {v.get('url')}" for k, v in shares.items())
        if args and args[0] in ("yes", "confirm", "go"):
            plan = _PENDING.get("plan")
            if not plan:
                return "Nothing previewed. Run /sharebot first."
            handle = next((a for a in args[1:] if a.strip("@")), "") or H._load_state().get(plan["name"], {}).get("handle", "")
            if not handle:
                return "Add your X/GitHub handle for credit: /sharebot yes @yourhandle"
            res = H.upload(plan, handle)
            _PENDING.clear()
            return (f"{res.get('message')}\nListing: {res.get('url')}\n"
                    "You'll get a live link once it's reviewed. Check with /sharebot mine.")
        opts = {"profile": None, "title": "", "tagline": ""}
        i = 0
        while i < len(args):
            a = args[i]
            for k in opts:
                if a == f"--{k}" and i + 1 < len(args):
                    opts[k] = args[i + 1]; i += 1
                elif a.startswith(f"--{k}="):
                    opts[k] = a.split("=", 1)[1]
            i += 1
        plan = H.pack(opts["profile"], title=opts["title"], tagline=opts["tagline"])
        _PENDING["opts"] = opts
        _PENDING["plan"] = plan
        return _fmt_plan(plan) + "\n\nLooks right? Run: /sharebot yes @yourhandle"
    except H.ShareError as e:
        return f"Not shared: {e}"


def _fmt_install(out: dict) -> str:
    lines = [f"Added {out.get('title')} as bot `{out['profile']}`."]
    if out["cron_paused"]:
        lines.append(f"{out['cron_paused']} schedule(s) arrived paused: `hermes -p {out['profile']} cron list`.")
    if out["mcp_disabled"]:
        lines.append(f"MCP servers off until you enable them: {', '.join(out['mcp_disabled'])}.")
    if out["env_requires"]:
        lines.append("Keys it can use: " + ", ".join(e["name"] for e in out["env_requires"]) +
                     f" (add to ~/.hermes/profiles/{out['profile']}/.env).")
    if out["hub_skills"]:
        lines.append("It suggests hub skills: " + ", ".join(out["hub_skills"][:8]) +
                     f". Install with `hermes -p {out['profile']} skills install <id>`.")
    lines.append(f"Chat with it: `hermes -p {out['profile']} chat`, or pick it in the desktop bot list.")
    return "\n".join(lines)


# ------------------------------------------------------------------ CLI ----
def _setup_cli(parser) -> None:
    sub = parser.add_subparsers(dest="hm_action")
    s = sub.add_parser("share", help="Preview and share a bot (profile) to hermesmade.lol")
    s.add_argument("--bot", "--profile", dest="profile", default=None, help="Bot (profile) to share (default: active)")
    s.add_argument("--handle", default="", help="Your @handle for credit")
    s.add_argument("--title", default="")
    s.add_argument("--tagline", default="")
    s.add_argument("--description", default="")
    s.add_argument("--skills", default=None, help="Comma list: only ship these of your own skills")
    s.add_argument("--no-cron", action="store_true", help="Do not ship schedules")
    s.add_argument("--yes", "-y", action="store_true", help="Upload without the confirm prompt")
    s.add_argument("--dry-run", action="store_true", help="Build and show the package, do not upload")
    a = sub.add_parser("add", help="Add a bot from hermesmade.lol")
    a.add_argument("bot", help="Bot id or hermesmade.lol/bots/... link")
    a.add_argument("--name", default=None, help="Local profile name")
    a.add_argument("--yes", "-y", action="store_true")
    sub.add_parser("mine", help="List bots you've shared from this machine")
    u = sub.add_parser("unshare", help="Delete one of your listings")
    u.add_argument("name")
    g = sub.add_parser("migrate-grok", help="Move your Grok Bot bots into Hermes, one Hermes bot each")
    g.add_argument("--file", action="append", default=None,
                   help="Export file or folder (repeatable; default: grok-bot-export*.json in Downloads, else paste)")
    g.add_argument("--bot", action="append", default=None, help="Only this Grok Bot (repeatable)")
    g.add_argument("--prompt", action="store_true", help="Print the export prompt to paste into each Grok Bot")
    g.add_argument("--dry-run", action="store_true", help="Show what would be created, write nothing")
    g.add_argument("--yes", "-y", action="store_true")


def _handle_cli(args) -> None:
    act = getattr(args, "hm_action", None)
    try:
        if act == "share":
            plan = H.pack(args.profile, title=args.title, tagline=args.tagline, description=args.description,
                          include_skills=[x.strip() for x in args.skills.split(",")] if args.skills else None,
                          include_cron=not args.no_cron)
            print(_fmt_plan(plan))
            print(f"\nPackage: {plan['archive']}")
            if args.dry_run:
                return
            handle = args.handle or H._load_state().get(plan["name"], {}).get("handle", "")
            if not handle:
                handle = input("Your @handle for credit: ").strip()
            if not args.yes and input("Upload to hermesmade.lol? [y/N] ").strip().lower() not in ("y", "yes"):
                print("Cancelled. Nothing left this machine.")
                return
            res = H.upload(plan, handle)
            print(f"\n{res.get('message')}\n{res.get('url')}")
        elif act == "add":
            pv = H.preview(args.bot)
            b = pv["bot"]
            m = b.get("meta") or {}
            print(f"{b['title']} by {b['owner_handle']} (v{b['version']}, {b['installs']} installs)")
            print(f"Installs as profile: {args.name or pv['install_as']}")
            print(f"Skills: {', '.join(m.get('skills') or []) or 'built-in only'}")
            if m.get("cron"):
                print("Schedules (paused): " + ", ".join(j["name"] for j in m["cron"]))
            if m.get("mcp"):
                print("MCP (off): " + ", ".join(x["name"] for x in m["mcp"]))
            for s in pv["scans"]:
                print(f"Scan {s['skill']}: {s['verdict']}" + (f" ({'; '.join(s['findings'][:2])})" if s["findings"] else ""))
            print("\n--- SOUL.md ---\n" + pv["soul"][:1500] + ("\n…" if len(pv["soul"]) > 1500 else ""))
            if pv["blocked"]:
                print("\nBlocked: the skill scanner rated this bot dangerous.")
                return
            if not args.yes and input("\nAdd this bot? [y/N] ").strip().lower() not in ("y", "yes"):
                print("Cancelled.")
                return
            print("\n" + _fmt_install(H.install(args.bot, name=args.name)))
        elif act == "mine":
            shares = H.my_shares()
            print("\n".join(f"{k}  v{v.get('version')}  {v.get('url')}" for k, v in shares.items()) or "Nothing shared yet.")
        elif act == "unshare":
            H.unshare(args.name)
            print(f"Deleted listing {args.name}.")
        elif act == "migrate-grok":
            _migrate_grok_cli(args)
        else:
            print("Usage: hermes hermesmade {share|add|mine|unshare|migrate-grok} --help")
    except H.ShareError as e:
        print(f"error: {e}")
        raise SystemExit(1)


def _migrate_grok_cli(args) -> None:
    import sys
    import hermesmade_migrate as G
    try:
        if not G.importer_installed():
            print(f"Moving bots from Grok Bot uses the official {G.PLUGIN} plugin from the Hermes catalog.")
            if not sys.stdin.isatty() or input(f"Install it now ({G.INSTALL_HINT})? [y/N] ").strip().lower() not in ("y", "yes"):
                print(f"Not installed. Run `{G.INSTALL_HINT}`, then try again.")
                raise SystemExit(1)
            G.install_importer()
        if args.prompt:
            print(G.export_prompt())
            return
        files, texts = args.file, None
        if not files:
            files = G.find_downloads() or None
            if files:
                print("Found in Downloads: " + ", ".join(files))
        if not files:
            print("Paste each Grok Bot's export reply below. Get it by pasting the prompt from\n"
                  "`hermes hermesmade migrate-grok --prompt` into that Bot's chat (open Grok Bot:\n"
                  "https://x.ai/bot/link/v1/open). Finish with Ctrl-D.\n")
            texts = [sys.stdin.read()]
        pv = G.preview(texts, files)
        for b in pv["bots"]:
            if args.bot and b["name"].lower() not in {x.lower() for x in args.bot}:
                continue
            verb = "tops up" if b["existing"] else "becomes"
            print(f"\n{b['name']}  {verb} Hermes bot '{b['profile']}'")
            print(f"  skills: {', '.join(b['skills']) or 'none'}")
            print(f"  routines (arrive paused): {', '.join(b['routines']) or 'none'}")
            if b["event_routines"]:
                print(f"  event routines (saved as notes to rebuild): {', '.join(b['event_routines'])}")
            print(f"  memories: {b['memories']}, facts about you: {b['user_facts']}")
            if b["apps"]:
                print(f"  apps: {', '.join(b['apps'])} (remote MCP URLs come over; logins stay in Grok Bot)")
        if args.dry_run:
            print("\nDry run: nothing written.")
            return
        if not args.yes and input("\nMigrate? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Cancelled. Nothing written.")
            return
        out = G.migrate(texts, files, only=args.bot)
        for r in out["results"]:
            s = r["summary"]
            print(f"\n{r['bot']} -> {r['profile']}  ({s.get('imported', 0)} imported, {s.get('skipped', 0)} skipped"
                  f"{', %d conflicts' % s['conflict'] if s.get('conflict') else ''})")
            if r["routines_paused"]:
                print(f"  {r['routines_paused']} routine(s) paused: turn the Grok copy off, then "
                      f"`hermes -p {r['profile']} cron resume <id>`")
            for n in r["notes"]:
                print(f"  note: {n}")
            print(f"  chat: `hermes -p {r['profile']} chat`, or pick it in the desktop bot list")
    except G.MigrateError as e:
        print(f"error: {e}")
        raise SystemExit(1)


# ----------------------------------------------------------------- tool ----
SCHEMA = {
    "name": "hermesmade_bots",
    "description": ("Share a Hermes bot (profile) to the community shelf at hermesmade.lol, or add a community bot. "
                    "action=preview builds the sanitized package and returns exactly what would ship. "
                    "action=share uploads it and REQUIRES the user to have seen the preview and said yes in this "
                    "conversation. action=add installs a bot by id/link (show the user the bot first). "
                    "action=mine lists the user's listings."),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["preview", "share", "add", "info", "mine"]},
            "profile": {"type": "string", "description": "Profile to share; omit for the active one"},
            "handle": {"type": "string", "description": "User's @handle for credit (share)"},
            "tagline": {"type": "string"},
            "description": {"type": "string"},
            "bot": {"type": "string", "description": "Bot id or hermesmade.lol link (add/info)"},
            "user_confirmed": {"type": "boolean", "description": "True only after the user explicitly approved this exact upload/install"},
        },
        "required": ["action"],
    },
}


def _tool(args: dict, **_kw) -> str:
    act = args.get("action")
    try:
        if act == "preview":
            plan = H.pack(args.get("profile"), tagline=args.get("tagline", ""), description=args.get("description", ""))
            _PENDING["plan"] = plan
            return json.dumps({"preview": _fmt_plan(plan), "next": "Show this to the user and ask before sharing."})
        if act == "share":
            if not args.get("user_confirmed"):
                return json.dumps({"error": "Ask the user to confirm the previewed package first."})
            plan = _PENDING.get("plan") or H.pack(args.get("profile"), tagline=args.get("tagline", ""),
                                                  description=args.get("description", ""))
            res = H.upload(plan, args.get("handle") or H._load_state().get(plan["name"], {}).get("handle", ""))
            _PENDING.clear()
            return json.dumps({k: v for k, v in res.items() if k != "manage_token"})
        if act == "info":
            pv = H.preview(args.get("bot", ""))
            return json.dumps({"bot": pv["bot"], "scans": pv["scans"], "soul": pv["soul"][:2000], "blocked": pv["blocked"]})
        if act == "add":
            if not args.get("user_confirmed"):
                return json.dumps({"error": "Show the user the bot (action=info) and get a yes first."})
            return json.dumps(H.install(args.get("bot", "")))
        if act == "mine":
            return json.dumps(H.my_shares())
        return json.dumps({"error": f"unknown action {act}"})
    except H.ShareError as e:
        return json.dumps({"error": str(e)})


def register(ctx) -> None:
    ctx.register_command("sharebot", _slash, description="Share this bot to hermesmade.lol, or add one",
                         args_hint="[--title T | yes @handle | add <id> | mine]")
    ctx.register_cli_command(name="hermesmade", help="Share bots to / add bots from hermesmade.lol",
                             description="Community bot shelf at hermesmade.lol.",
                             setup_fn=_setup_cli, handler_fn=_handle_cli)
    ctx.register_tool(name="hermesmade_bots", toolset=TOOLSET, schema=SCHEMA, handler=_tool,
                      description=SCHEMA["description"])


__all__ = ["register"]
