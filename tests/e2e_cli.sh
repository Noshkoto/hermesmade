#!/usr/bin/env bash
# Full-path test through the REAL CLI: plugins install (from the worker-served
# git repo) -> share -> admin approve -> add on a second "machine".
# Sandboxed HOMEs; never touches ~/.hermes. Usage: e2e_cli.sh <site-url> <admin-secret>
set -uo pipefail
SITE="$1"; ADMIN="$2"
AG="${HERMES_AGENT_DIR:-$HOME/.hermes/hermes-agent}"
SB=$(mktemp -d)
run() { # home cmd...
  local h="$1"; shift
  (cd "$AG" && env -i HOME="$h" PATH="$AG/venv/bin:/usr/bin:/bin" HERMESMADE_URL="$SITE" TERM=dumb \
     "$AG/venv/bin/python" -m hermes_cli.main "$@" 2>&1 | grep -v "out of sync")
}
for who in author installer; do
  H="$SB/$who/.hermes"; mkdir -p "$H"
  printf 'model:\n  provider: nous\n  default: model-of-%s\n' "$who" > "$H/config.yaml"
done
A="$SB/author"; I="$SB/installer"
inst() { # home
  mkdir -p "$1/bin"; printf '#!/bin/sh\ncd %s && exec %s/venv/bin/python -m hermes_cli.main "$@"\n' "$AG" "$AG" > "$1/bin/hermes"; chmod +x "$1/bin/hermes"
  curl -fsSL "$SITE/install.sh" | env -i HOME="$1" PATH="$1/bin:/usr/bin:/bin" HERMESMADE_URL="$SITE" sh 2>&1 | grep -v "out of sync" | tail -3
}
printf "## site installer (author)\n"
inst "$A"
printf "## site installer (installer)\n"
inst "$I"
grep -A3 "^plugins:" "$A/.hermes/config.yaml"
run "$A" profile create gardener --no-alias | tail -1
P="$A/.hermes/profiles/gardener"
cat > "$P/SOUL.md" <<'EOF'
# Gardener
You are Gardener, a patient vegetable-garden coach. You plan plantings by frost date and never guess at pesticide safety.
EOF
mkdir -p "$P/skills/garden/frost-planner"
printf -- '---\nname: frost-planner\ndescription: plan sowing from frost dates\n---\nAsk for the ZIP, look up the last frost date, build a sowing calendar.\n' > "$P/skills/garden/frost-planner/SKILL.md"
echo "OPENROUTER_API_KEY=sk-or-v1-$(printf 'k%.0s' {1..48})" >> "$P/.env"
echo "## untitled default must refuse"
run "$A" hermesmade share --dry-run | tail -1
echo "## share gardener"
run "$A" hermesmade share --bot gardener --handle nosh --tagline "Plans your garden by frost date." --yes | tail -3
ID=$(python3 -c "import json;print(list(json.load(open('$A/.hermes/hermesmade/shared.json')).values())[0]['id'])")
echo "bot id $ID"
grep -c manage_token "$A/.hermes/hermesmade/shared.json" >/dev/null && echo "manage token stored locally ($(stat -c %a "$A/.hermes/hermesmade/shared.json"))"
curl -s -X POST -H "x-admin-key: $ADMIN" "$SITE/api/admin/bots/$ID/approve" | head -c 60; echo
echo "## add on installer"
run "$I" hermesmade add "$SITE/bots/$ID-gardener" --yes | tail -8
run "$I" profile list | grep -E "gardener|default"
echo "## leak check on installed bot"
grep -rl "sk-or-v1" "$I/.hermes/profiles/gardener" && echo LEAK || echo "no key anywhere in installed bot"
grep -E "default:" "$I/.hermes/profiles/gardener/config.yaml"
echo "## agent tool registered?"
run "$I" tools list 2>/dev/null | grep -i hermesmade | head -2
echo "## /sharebot mine via slash (author)"
(cd "$AG" && env -i HOME="$A" PATH="$AG/venv/bin:/usr/bin:/bin" HERMESMADE_URL="$SITE" "$AG/venv/bin/python" - <<'PY'
from hermes_cli.plugins import discover_plugins, get_plugin_command_handler
discover_plugins()
h = get_plugin_command_handler("sharebot")
print("sharebot handler:", bool(h)); print(h("mine") if h else "")
PY
) 2>&1 | grep -v "out of sync" | tail -3
echo "SANDBOX $SB"
