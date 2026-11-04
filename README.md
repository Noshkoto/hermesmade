# hermesmade — community Hermes bots

Share your Hermes bots to [hermesmade.lol/bots](https://hermesmade.lol/bots) and add other people's bots in one click.

```bash
hermes plugins install https://hermesmade.lol/plugin.git --enable
```

## Share a bot

In any chat with the bot:

```
/sharebot --title "Chef" --tagline "Plans your week of dinners."
/sharebot yes @yourhandle
```

or `hermes hermesmade share -p <profile>`, or **Community bots → Share a bot** in the desktop app.

You see the exact file list before anything uploads. A shared bot is a Hermes profile
distribution: `SOUL.md`, a cleaned `config.yaml`, your own skills, and schedules.

Never shipped: `.env`, `auth.json`, API keys, bot tokens, MCP credentials, Discord/Telegram
settings, memories, sessions, chat history, your model login. Every file is pattern-scanned
for keys and checked against your own `.env` values; one hit aborts the share. The server
scans again before accepting the upload, and every listing is reviewed before it goes live.

## Add a bot

Press **Add bot** on hermesmade.lol (opens `hermes://open/hermesmade?add=<id>`), or:

```bash
hermes hermesmade add <id>
```

Added bots run on your own model and login. Schedules arrive paused, MCP servers arrive off,
and Hermes' skill scanner checks every bundled skill first. Anything rated dangerous is refused.

## Commands

| | |
|---|---|
| `/sharebot` | preview / `yes @handle` / `add <id>` / `mine` |
| `hermes hermesmade share\|add\|mine\|unshare` | CLI |
| `hermesmade_bots` | agent tool (asks before uploading or installing) |

MIT licensed.
