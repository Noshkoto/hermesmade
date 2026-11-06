# hermesmade: community Hermes bots

Share your Hermes bots to [hermesmade.lol/bots](https://hermesmade.lol/bots), add other people's bots in one click, and move your Grok Bot bots into Hermes.

```bash
hermes plugins install hermesmade
```

Restart Hermes (or the desktop app) after installing. A **Community bots** page appears in the desktop sidebar.

## Add a bot

Press **Add bot** on hermesmade.lol (it opens `hermes://open/hermesmade?add=<id>`), or run:

```bash
hermes hermesmade add <id>
```

The desktop page shows the bot's personality, skills, schedules, MCP servers and Hermes's skill-scan result before anything installs. Each added bot becomes its own Hermes profile and runs on your model and login. Schedules arrive paused and MCP servers arrive off. A bot whose skills the scanner rates dangerous is refused.

## Share a bot

In a chat with the bot:

```
/sharebot --title "Chef" --tagline "Plans your week of dinners."
/sharebot yes @yourhandle
```

You can also run `hermes hermesmade share --bot <name>`, or use **Community bots → Share a bot** in the desktop app.

You see the exact file list before anything uploads. A shared bot is a Hermes profile distribution: `SOUL.md`, a cleaned `config.yaml`, your own skills and your schedule definitions.

Never shipped: `.env`, `auth.json`, API keys, bot tokens, MCP credentials, messaging-platform settings, memories, sessions, chat history or your model login. Every file is pattern-scanned for keys and compared against your profile's own secret values. A single hit aborts the share. The server scans again on upload, and a moderator reviews every listing and update before it goes live.

## Move from Grok Bot

Grok Bot has no export button, so each Bot exports itself. Open **Community bots → Move from Grok Bot** in the desktop app, or follow the guide at [hermesmade.lol/bots/from-grok](https://hermesmade.lol/bots/from-grok):

1. Copy the export prompt.
2. Open Grok Bot and paste the prompt into each Bot's chat. The Bot replies with a JSON export and saves it to Downloads when it can.
3. Come back to Hermes. It finds the exports in Downloads, or takes a pasted reply, and shows every Bot before creating anything.

Each Grok Bot becomes its own Hermes bot, keeping its instructions, skills, memories and facts about you. Scheduled routines become cron jobs on the same schedule and time zone, **paused**, so nothing runs twice; resume one after you turn its Grok copy off. Apps with a remote MCP URL become MCP servers you sign in to again. Event-triggered routines become a notes file to rebuild. An export that contains anything that looks like a key is refused, not trimmed. Running the migration again only adds what is new.

The JSON is read by [agent-importers](https://hermes-agent.nousresearch.com/docs/plugins/agent-importers), the official Nous importer. The first time you use this flow, Hermes asks before installing agent-importers from the plugin catalog.

The same flow in a terminal:

```bash
hermes hermesmade migrate-grok --prompt   # print the prompt to paste
hermes hermesmade migrate-grok            # preview, confirm, migrate
```

## Commands

| | |
|---|---|
| `/sharebot` | preview / `yes @handle` / `add <id>` / `mine` |
| `hermes hermesmade share\|add\|mine\|unshare\|migrate-grok` | CLI |
| `hermesmade_bots` | agent tool (asks before uploading or installing) |

## What this plugin does on your machine (disclosure)

- **Network:** it talks only to `https://hermesmade.lol` (set `HERMESMADE_URL` to change this), and only when you browse, add, share or unshare a bot. There is no telemetry and no background traffic. The Grok Bot flow makes no network calls, apart from opening x.ai's "Open Grok Bot" page in your browser when you press that button.
- **Writes:** it creates Hermes profiles under `~/.hermes/profiles/<name>` (one per added or migrated bot) and keeps a record of your shared listings in `~/.hermes/hermesmade/shared.json` (mode 600). The record holds each listing's manage token, which is needed to update or delete it.
- **Reads:**
  - When sharing, the chosen profile's `SOUL.md`, `config.yaml`, skills and cron definitions.
  - Its secret values, through Hermes's secret scope, only to block a share that would leak one. Values are compared in memory and never stored or sent.
  - When migrating, `grok-bot-export*.json` files in your Downloads folder.
- **Never touched:** Grok Bot's own files, cookies or login.
- **Subprocess:** after you confirm, it runs `hermes plugins install agent-importers --enable` once to install the official importer.
- **No self-updates:** updates arrive only through the plugin catalog.

MIT licensed.
