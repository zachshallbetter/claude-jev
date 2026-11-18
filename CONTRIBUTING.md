# Contributing

Thanks for helping. This is a Claude Code plugin that puts Jev, a typed-decision model, inside Claude Code.

## Setup

You need Python 3.10 or later. The scripts use the standard library only, so there is nothing to install. The
manifest check also uses the `claude` CLI.

```bash
python3 -m unittest discover -s skills/jev/tests    # the test suite
claude plugin validate .                            # the plugin and marketplace manifests
```

The tests run a fake System One server on loopback; nothing reaches the network. CI runs the same suite on pull
requests and pushes to `main`, and checks that `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`
agree on the version and that the hook and preset JSON files parse.

## Conventions

- Standard library only in `skills/jev/scripts/`. `jev.py` stays a single file so it can be copied into another
  program.
- A credential is never printed, logged, written to disk or echoed. Examples and tests use fictional names only.
- Anything that sends text to a provider must stay opt-in, and the permission gate must stay approve-only, with its
  static risk list in code.
- A release bumps the version in both `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`, adds a
  [CHANGELOG.md](CHANGELOG.md) entry and is tagged `vX.Y.Z`.
- Commit titles are short and descriptive, in the form `jev plugin 0.1.5: what changed` for releases and
  `ci: ...` for workflow changes. Pull requests are merged by the maintainer.

## Security

Report vulnerabilities privately, as [SECURITY.md](SECURITY.md) describes, not in a public issue.
