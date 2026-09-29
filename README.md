# jev — a Claude Code plugin

[Jev](https://typesafe.ai) is TypeSafe's "System One" decision model: typed answers (pick one
of several options, a 1–N score, or yes/no) with calibrated confidence, in about 0.3 s, for
about $0.04 per million input tokens. This plugin puts it inside Claude Code:

- **`/jev:jev sort | ask | route`**: sort, triage, flag or score a pile of text (emails, tickets,
  invoices, logs, folders) with built-in presets or your own questions.
- **`/jev:jev calibrate`**: check whether Jev's confidence can be trusted on your own labelled
  examples before relying on a threshold.
- **Building Jev into code**: patterns for routing, guardrails, reranking, typed function
  calling and tool-call gating (`skills/jev/references/building.md`).
- **Prompt router** (`/jev:jev on`, off by default): Jev sizes each prompt and suggests one of
  the bundled `jev-haiku / jev-sonnet / jev-opus / jev-fable` helper agents.
- **Permission gate** (`/jev:jev perms on`, off by default): auto-approves Bash commands Jev
  is sure are routine; anything else is left to you. It never denies.

Claude also uses the skill without the slash command when you ask, for example, "use Jev to sort
these".

## Install

```text
/plugin marketplace add zachshallbetter/claude-jev
/plugin install jev@claude-jev
```

The repository is private, so the machine needs git access to it (`gh auth login` or an SSH key).
Updates: `/plugin marketplace update claude-jev`, or turn on auto-update for the marketplace in
`/plugin`.

To have a project offer it automatically, add to that project's `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "claude-jev": { "source": { "source": "github", "repo": "zachshallbetter/claude-jev" } }
  },
  "enabledPlugins": { "jev@claude-jev": true }
}
```

## Credentials

Checked in this order; the first one found wins:

| Where | Setting |
|---|---|
| Broker (no provider key on the machine) | `JEV_AUTH=coordinator`, `JEV_BASE_URL=<decision-broker>`, `JEV_COORDINATOR_KEY_FILE=<Ed25519 private PEM>`, optional `JEV_COORDINATOR_ID` |
| Any provider | `JEV_API_KEY` (+ `JEV_BASE_URL`, default OpenRouter) |
| TypeSafe direct | `TYPESAFE_API_KEY` (+ `TYPESAFE_BASE_URL`) |
| OpenRouter | `OPENROUTER_API_KEY` |
| macOS Keychain | item `jev-openrouter` or `jev-typesafe` |

Store a Keychain key without it touching chat or shell history:

```bash
security add-generic-password -U -a "$USER" -s jev-openrouter -w
```

Then run `/jev:jev doctor` and `/jev:jev test`.

## State

Switches and the usage log (latency, tokens and cost per call, never the content) live in
`$JEV_HOME`, default `~/.claude/jev`, so they survive plugin updates and reinstalls.

## Moving from the user-level skill

If `~/.claude/skills/jev` is also installed, remove its hooks first
(`python3 ~/.claude/skills/jev/scripts/jev.py uninstall`), or every hook runs twice.
`/jev:jev doctor` flags this.

## Development

Stdlib-only Python 3.10+. Tests: `python3 -m unittest discover -s skills/jev/tests`.
Validate: `claude plugin validate .`
