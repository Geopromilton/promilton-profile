# tools/

Standalone utilities. Not part of the profile site — nothing here is served or linked
from the HTML pages in the repo root.

## `omniroute-claude-code.sh`

Configures the **Claude Code CLI** to route through [OmniRoute](https://www.npmjs.com/package/omniroute),
a local AI gateway on `localhost:20128` that serves the native Anthropic Messages format
at `/v1/messages` — the wire protocol Claude Code already speaks, so no translation shim
is involved.

Run it on the machine where OmniRoute is running.

```bash
./omniroute-claude-code.sh check          # preflight only; changes nothing
./omniroute-claude-code.sh models free    # list model ids matching "free"
./omniroute-claude-code.sh setup          # default: auto/best-free
./omniroute-claude-code.sh setup auto/best-coding
./omniroute-claude-code.sh verify         # end-to-end test through the claude CLI
./omniroute-claude-code.sh revert         # remove the block + GUI-level leftovers
```

### What it does

1. Proves the gateway answers in Anthropic format before touching any config. If the
   gateway is down, it writes nothing and exits non-zero.
2. Validates the model id against `/v1/models`. Bare provider names (`openrouter`,
   `groq`, …) are rejected with the ids that provider actually exposes, since a provider
   is not a model. Bare names that aren't providers are treated as dashboard combos,
   which resolve on their own and often aren't listed.
3. Reports conflicting model pins in `~/.claude/settings.json` (and the project-local and
   `.local.json` variants). **It does not edit those files** — they're yours and may hold
   unrelated configuration.
4. Writes an idempotent, marker-delimited block to `~/.zshrc` (macOS) or `~/.bashrc`
   (Linux), backing up the file first if a previous block exists.

Precedence, highest wins: `--model` flag → `settings.json` `env` → shell environment.

### Prerequisites

```bash
npm install -g omniroute
omniroute setup     # add at least one provider key
omniroute           # keep running in its own terminal
```

A model only routes if you hold a provider key that serves it — check with
`omniroute keys list`.

### Desktop app

Out of scope, and the script has no mode for it. The Claude Desktop app authenticates
with a Claude subscription over OAuth, and an OAuth token is only valid against
Anthropic's own endpoint — so the app pins `ANTHROPIC_BASE_URL` to its internal API host
and blanks `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_CUSTOM_HEADERS` on
the agent child process. `launchctl setenv`, a Launch Agent plist, and
`settings.json` are all equally ineffective: `settings.json` can set the base URL *only*
when nothing else already has, and the app always has. Use the CLI for gateway work.
