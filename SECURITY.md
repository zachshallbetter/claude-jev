# Security

## Reporting

Report a vulnerability privately through GitHub's "Report a vulnerability" on this repository, or by email to the address on the maintainer's GitHub profile. Please do not open a public issue for anything that could expose a user's data or credentials. Expect an acknowledgement within a few days.

## What this plugin can touch

- **Credentials.** A provider key comes from an environment variable or the macOS Keychain and is used only as a bearer header on calls to the configured base URL. It is never printed, logged, written to disk by the plugin, or echoed in chat. In broker mode no provider key exists on the machine. For a local server (loopback or private address, no key set) no `Authorization` header is sent at all.
- **Outbound data.** Text you pass to `sort`, `ask`, `route`, `calibrate`, or that the prompt router reads when it is switched on, goes to the configured provider. Nothing is sent without that configuration, and `sort` refuses to send without `--yes`. Redaction and length caps are available. The usage log holds latency, tokens and cost only.
- **The permission gate.** When switched on, it sees the command line of a Bash call Claude Code is about to prompt for. A static risk list in code decides what is never sent and always prompts: destructive commands, pushes and resets, deploys, remote shells, network writes, databases, service managers, `sudo`, redirects and substitutions, and anything that references env files, secrets, keys or tokens. The gate can only approve; it never denies, and user deny rules take precedence. It is off by default.
- **Hooks.** With the router off, the prompt hook reads one small state file and exits. Hook commands are fixed strings in `hooks/hooks.json`; nothing in a prompt or tool output is executed.

## Supported versions

The latest tagged release. Older tags receive no fixes.
