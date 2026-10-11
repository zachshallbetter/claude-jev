# Changelog

All notable changes to the jev plugin. Versions are tagged `vX.Y.Z`; the same number appears in `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`.

## 0.1.5 — 2026-10-10

First public release.

- Dual license, MIT OR Apache-2.0. License, homepage and repository fields in the plugin manifest.
- README rewritten for public install: what leaves your machine, credential order including a local System One server, embedding guidance.
- `SECURITY.md`, this changelog, and a CI workflow that runs the test suite on Python 3.10 and 3.12 and validates the manifests.
- The embedded-copy drift check is generic: `JEV_EMBEDDED_COPY`, or `set embedded_copy <path>`, names the copy; nothing is checked when neither is set.
- Examples and tests use fictional names only. Scripts carry their executable bit again.

## 0.1.4 — 2026-10-10

- A local System One server is recognised: `JEV_BASE_URL` on loopback or a private address with no `JEV_API_KEY` sends no bearer, pins to the local model unless `JEV_MODEL` says otherwise, and costs $0 when the server states no cost.
- Tests: the hosted-base test presents the loopback fake as hosted; a new suite covers `_is_local` and a keyless local call.

## 0.1.3 — 2026-09-30

- Documented the decision-broker path: turn gates, `JEV_AUTH=coordinator`, decision origin, the shadow trial. `building.md` gained a "Through a decision-broker" section.

## 0.1.2 — 2026-09-30

- `decide(..., origin={source, person, role})` sends `X-Decision-Source`, `-Person` and `-Role` headers to a decision-broker so its readouts can separate real turns from canaries, evals and tests. Sent only in broker mode, never to a model provider.

## 0.1.1 — 2026-09-29

- State and the settings file follow `CLAUDE_CONFIG_DIR` when Claude Code runs with a non-default config directory.
- Tests cover plugin mode: install writes nothing into settings, doctor checks the plugin's hooks and flags leftover user-level hooks, helper agents are named `jev:jev-<tier>`.

## 0.1.0 — 2026-09-29

- The `/jev` skill packaged as a Claude Code plugin that is also its own marketplace: skill, scripts, presets, references, tests; hooks for the prompt router and permission gate, both off until switched on; the four `jev-<tier>` helper agents.
- Left out on purpose: calibration sets built from one machine's project folders, and a hardcoded list of GitHub owners.
