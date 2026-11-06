"""E2E phase script. Phase from argv. HOME is redirected per phase so Hermes
roots resolve to the sandbox; never touches ~/.hermes or hermesmade.lol."""
import json, os, sys, tarfile, gzip, textwrap, urllib.request
from pathlib import Path
PHASE = sys.argv[1]
SB = Path(os.environ["HM_SB"])
AUTHOR = SB / "author-home" / ".hermes"
INSTALLER = SB / "installer-home" / ".hermes"
home = (INSTALLER if PHASE == "installer" else AUTHOR)
home.mkdir(parents=True, exist_ok=True)
os.environ["HOME"] = str(home.parent)
os.environ.pop("HERMES_HOME", None)
os.environ["HERMES_SHARED_AUTH_DIR"] = str(SB / "shared-" + PHASE) if False else str(SB / ("shared-" + PHASE))
os.environ.setdefault("HERMESMADE_URL", "http://localhost:8798")
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, os.environ.get("HERMES_AGENT_DIR", os.path.expanduser("~/.hermes/hermes-agent")))
FAKE_OR = "sk-or-v1-" + "a" * 48
FAKE_DISCORD = "MTA" + "x" * 21 + ".AbCdEf." + "y" * 30
LITERAL = "zq9" * 8  # opaque .env value with no vendor shape

if PHASE == "author":
  pass

import hermesmade_share as H
if PHASE == "author":
    prof = AUTHOR / "profiles" / "chef-bot"
    (prof / "skills" / "cooking" / "meal-planner").mkdir(parents=True)
    (prof / "skills" / "cooking" / "meal-planner" / "SKILL.md").write_text(
        "---\nname: meal-planner\ndescription: plan weekly meals\n---\n# Meal planner\nUse SPOONACULAR_API_KEY when present. Plan 7 dinners.\n")
    (prof / "skills" / "cooking" / "meal-planner" / ".env").write_text(f"SPOONACULAR_API_KEY={LITERAL}\n")
    (prof / "skills" / "bundled-thing").mkdir(parents=True)
    (prof / "skills" / "bundled-thing" / "SKILL.md").write_text("---\nname: bundled-thing\ndescription: x\n---\nx\n")
    (prof / "skills" / ".bundled_manifest").write_text("bundled-thing:abc\n")
    (prof / "SOUL.md").write_text("# Chef\nYou are Chef, a warm and precise home-cooking assistant. You plan meals, scale recipes and never invent nutrition facts.\n")
    (prof / ".env").write_text(f"OPENROUTER_API_KEY={FAKE_OR}\nDISCORD_BOT_TOKEN={FAKE_DISCORD}\nSPOONACULAR_API_KEY={LITERAL}\n")
    (prof / "auth.json").write_text('{"secret": "x"}')
    (prof / "memories").mkdir(); (prof / "memories" / "MEMORY.md").write_text("User lives at 1 Private St.")
    (prof / "sessions").mkdir(); (prof / "sessions" / "s.json").write_text("{}")
    (prof / "config.yaml").write_text(textwrap.dedent(f"""\
    model:
      provider: openrouter
      default: anthropic/claude-sonnet-5
      api_key: {FAKE_OR}
    providers:
      openrouter:
        api_key: {FAKE_OR}
    discord:
      token: {FAKE_DISCORD}
      allowed_users: ["1234"]
    agent:
      max_turns: 40
      personalities:
        chef: "be warm"
      environment_hint: "/home/author/secret-project"
    display:
      personality: chef
    mcp_servers:
      recipes:
        url: https://mcp.recipes.example/sse
        headers:
          Authorization: Bearer {FAKE_OR}
      pantry:
        command: npx
        args: ["-y", "pantry-mcp"]
        env:
          PANTRY_TOKEN: {LITERAL}
      leaky:
        url: https://mcp.example/sse?api_key=abc123
    """))
    (prof / "profile.yaml").write_text("display_name: Chef\nui_meta:\n  hermes-bots:\n    title: Chef\n")
    (prof / "cron").mkdir()
    (prof / "cron" / "jobs.json").write_text(json.dumps({"jobs": [
        {"id": "j1", "name": "sunday plan", "prompt": "Plan next week's dinners", "schedule": {"kind": "cron", "expr": "0 9 * * 0", "display": "0 9 * * 0"}, "enabled": True, "state": "scheduled", "deliver": "discord:999"},
        {"id": "j2", "name": "local backup", "prompt": "x", "script": "backup.sh", "schedule": {"kind": "interval", "minutes": 60}, "enabled": True},
    ]}))
    (AUTHOR / "config.yaml").write_text("model:\n  provider: nous\n  default: hermes-5\n")
    
    plan = H.pack("chef-bot", tagline="Plans your week of dinners.", description="Chef plans meals and scales recipes.")
    print("PACK", plan["name"], plan["version"], plan["bytes"], "B")
    print(" files:", plan["files"])
    print(" skills:", plan["skills"], "cron:", plan["cron"], "mcp:", [m["name"] for m in plan["mcp"]])
    print(" warnings:", plan["warnings"])
    
    # Leak audit over the raw archive bytes and every member.
    blob = Path(plan["archive"]).read_bytes()
    import gzip
    raw = gzip.decompress(blob).decode("latin1")
    for label, needle in [("openrouter key", FAKE_OR), ("discord token", FAKE_DISCORD), ("literal .env value", LITERAL),
                          ("abc123 url key", "abc123"), ("private path", "secret-project"), ("memory", "Private St"),
                          ("discord user", "1234\""), ("deliver target", "discord:999")]:
        print(f" leak[{label}]:", "LEAKED" if needle in raw else "clean")
    with tarfile.open(plan["archive"]) as tf:
        names = tf.getnames()
    assert not any(n.endswith((".env", "auth.json")) or "/memories" in n or "/sessions" in n for n in names), names
    
    res = H.upload(plan, "nosh")
    print("UPLOAD", res["status"], res["id"], res["url"])
    assert "manage_token" not in json.dumps(H.my_shares())
    
    def admin(path, method="GET"):
        r = urllib.request.Request(os.environ["HERMESMADE_URL"] + path, method=method, data=b"" if method == "POST" else None,
                                   headers={"x-admin-key": "localtestsecret"})
        return json.loads(urllib.request.urlopen(r).read())
    pend = admin("/api/admin/bots/pending")["rows"]
    print("PENDING", [(b["id"], b["title"], b["status"]) for b in pend])
    try:
        H.fetch_info(str(res["id"])); print("BUG: pending bot visible publicly")
    except H.ShareError as e:
        print("pending hidden from public:", e)
    admin(f"/api/admin/bots/{res['id']}/approve", "POST")
    
    
    (SB / "bot_id").write_text(str(res["id"]))
else:
    BOT_ID = (SB / "bot_id").read_text().strip()
    (INSTALLER / "config.yaml").write_text("model:\n  provider: nous\n  default: hermes-5-installer\n")
    pv = H.preview(str(BOT_ID))
    print("PREVIEW install_as", pv["install_as"], "blocked", pv["blocked"], "scans", [(s["skill"], s["verdict"]) for s in pv["scans"]])
    out = H.install(str(BOT_ID))
    print("INSTALL", out["profile"], out["path"])
    p = Path(out["path"])
    print(" tree:", sorted(x.name for x in p.iterdir()))
    cfg = (p / "config.yaml").read_text()
    print(" config model ->", [l for l in cfg.splitlines() if "default" in l or "provider" in l][:3])
    print(" mcp enabled flags:", [l.strip() for l in cfg.splitlines() if "enabled" in l])
    jobs = json.loads((p / "cron" / "jobs.json").read_text())["jobs"]
    print(" cron:", [(j["name"], j.get("enabled"), j.get("state")) for j in jobs])
    print(" skill shipped:", (p / "skills" / "cooking" / "meal-planner" / "SKILL.md").is_file(),
          " skill .env shipped:", (p / "skills" / "cooking" / "meal-planner" / ".env").exists())
    print(" .env has secrets:", FAKE_OR in (p / ".env").read_text() if (p / ".env").exists() else False)
    print(" profile.yaml:", (p / "profile.yaml").read_text().replace("\n", " | ")[:300])
    print(" bundled seeded:", len(list((p / "skills").rglob("SKILL.md"))))
    info = H.fetch_info(str(BOT_ID))
    print("INSTALLS COUNT", info["installs"])
if PHASE == "reshare":
    p2 = H.pack("chef-bot", tagline="Plans your week of dinners. v2")
    r2 = H.upload(p2, "nosh")
    print("RESHARE", p2["version"], "same id:", str(r2["id"]) == (SB / "bot_id").read_text().strip(), r2["status"])
    # tamper: someone else tries to update without the token
    import urllib.request as U
    body, ct = H._multipart({"handle": "evil", "bot_id": str(r2["id"])}, "package", Path(p2["archive"]))
    code, raw = H._request("POST", "/api/bots", data=body, headers={"Content-Type": ct, "x-manage-token": "wrong"})
    print("HIJACK attempt ->", code, raw[:80])
    # a package with a secret slipped into SOUL must be rejected by the SERVER too
    import shutil, tempfile
    w = Path(tempfile.mkdtemp())
    with tarfile.open(p2["archive"]) as tf: tf.extractall(w, filter="data")
    soul = w / "chef-bot" / "SOUL.md"; soul.write_text(soul.read_text() + "\nkey: sk-ant-" + "q"*40 + "\n")
    bad = w / "bad.tar.gz"
    with tarfile.open(bad, "w:gz") as tf: tf.add(w / "chef-bot", arcname="chef-bot")
    body, ct = H._multipart({"handle": "evil"}, "package", bad)
    code, raw = H._request("POST", "/api/bots", data=body, headers={"Content-Type": ct})
    print("SERVER secret scan ->", code, raw[:120])
    # path traversal
    t = w / "trav.tar.gz"
    with tarfile.open(t, "w:gz") as tf:
        tf.add(w / "chef-bot", arcname="chef-bot")
        ti = tarfile.TarInfo("chef-bot/../../etc/x"); data=b"x"; ti.size=1
        import io; tf.addfile(ti, io.BytesIO(data))
    body, ct = H._multipart({"handle": "evil"}, "package", t)
    code, raw = H._request("POST", "/api/bots", data=body, headers={"Content-Type": ct})
    print("SERVER traversal ->", code, raw[:120])
    # .env smuggled under a skill
    e = w / "chef-bot" / "skills" / "cooking" / "meal-planner" / ".env"; e.write_text("X=1")
    soul.write_text("# Chef\nYou are Chef, a warm and precise home-cooking assistant who plans meals.\n")
    t2 = w / "env.tar.gz"
    with tarfile.open(t2, "w:gz") as tf: tf.add(w / "chef-bot", arcname="chef-bot")
    body, ct = H._multipart({"handle": "evil"}, "package", t2)
    code, raw = H._request("POST", "/api/bots", data=body, headers={"Content-Type": ct})
    print("SERVER .env in skill ->", code, raw[:120])
