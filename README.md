# jev — a Claude Code plugin

[Jev](https://typesafe.ai) is TypeSafe's "System One" decision model: typed answers (pick one of several options, a 1–N score, or yes/no) with calibrated confidence, in about 0.3 s, for about $0.04 per million input tokens. It never generates text, so there is nothing to hallucinate. This plugin puts it inside Claude Code and keeps the division of labour explicit: **Jev decides, Claude writes.**

- **`/jev:jev sort | ask | route`**: sort, triage, flag or score a pile of text (emails, tickets, invoices, logs, folders) with built-in presets or your own questions. Dry run first, consent before anything leaves the machine, an "unsure" pile you judge yourself.
- **`/jev:jev calibrate`**: measure whether Jev's confidence can be trusted on your own labelled examples before relying on a threshold. Ships with a 66-message household set and an HTML report.
- **Building Jev into code**: patterns for routing, guardrails, reranking, typed function calling and tool-call gating, in [`skills/jev/references/building.md`](skills/jev/references/building.md). The script doubles as an importable library.
- **Prompt router** (`/jev:jev on`, off by default): Jev sizes each prompt and suggests one of the bundled `jev-haiku / jev-sonnet / jev-opus / jev-fable` helper agents.
- **Permission gate** (`/jev:jev perms on`, off by default): auto-approves Bash commands Jev is sure are routine. A static risk list in code is the security boundary; the gate never denies, and your own deny rules still win.

Claude also uses the skill without the slash command when you ask, for example, "use Jev to sort these".

## Install

```text
/plugin marketplace add zachshallbetter/claude-jev
/plugin install jev@claude-jev
```

Updates: `/plugin marketplace update claude-jev` then `/plugin update jev@claude-jev`, or turn on auto-update for the marketplace in `/plugin`.

To have a project offer it automatically, add to that project's `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "claude-jev": { "source": { "source": "github", "repo": "zachshallbetter/claude-jev" } }
  },
  "enabledPlugins": { "jev@claude-jev": true }
}
```

Requirements: Python 3.10+ on the machine. No packages to install; the scripts use the standard library only.

## Credentials

Checked in this order; the first one found wins:

| Where | Setting |
|---|---|
| Broker (no provider key on the machine) | `JEV_AUTH=coordinator`, `JEV_BASE_URL=<decision-broker>`, `JEV_COORDINATOR_KEY_FILE=<Ed25519 private PEM>`, optional `JEV_COORDINATOR_ID` |
| Local System One server | `JEV_BASE_URL` on loopback or a private address, no `JEV_API_KEY`: no key is sent and calls cost $0 |
| Any provider | `JEV_API_KEY` (+ `JEV_BASE_URL`, default OpenRouter) |
| TypeSafe direct | `TYPESAFE_API_KEY` (+ `TYPESAFE_BASE_URL`) |
| OpenRouter | `OPENROUTER_API_KEY` |
| macOS Keychain | item `jev-openrouter` or `jev-typesafe` |

Store a Keychain key without it touching chat or shell history:

```bash
security add-generic-password -U -a "$USER" -s jev-openrouter -w
```

Then run `/jev:jev doctor` and `/jev:jev test`. The key is never printed, logged or written by the plugin.

## What leaves your machine

Only what you send. `sort`, `ask`, `route`, `calibrate` and the prompt router send the text they are given to the configured provider (TypeSafe directly, OpenRouter, a broker you run, or a local server). `sort` refuses to send without `--yes` and offers `--redact` (URLs, emails, paths, IPs, serial and key-like tokens) and `--max-chars`. The permission gate sends the command line of a Bash call that is not on the static risk list; commands that touch secrets, env files, tokens, deploys or destructive operations are never sent. The usage log records latency, tokens and cost per call, never the content. With the router off, the prompt hook reads one small state file and exits.

## State

Switches and the usage log live in `$JEV_HOME`, default `~/.claude/jev` (or under `CLAUDE_CONFIG_DIR`), so they survive plugin updates and reinstalls.

## Embedding the client elsewhere

`skills/jev/scripts/jev.py` is a single stdlib-only file so it can be copied into another program. If you keep a copy, point `JEV_EMBEDDED_COPY` at it and `/jev:jev doctor` reports when the two drift apart below the header docstring.

## Development

```bash
python3 -m unittest discover -s skills/jev/tests
claude plugin validate .
```

The tests run a fake System One server on loopback; nothing reaches the network. CI runs the suite on Python 3.10 and 3.12 and validates the manifests. Releases are tagged `vX.Y.Z` and the version lives in both `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`. See [CHANGELOG.md](CHANGELOG.md) and [SECURITY.md](SECURITY.md).

## License

MIT OR Apache-2.0, at your option.
