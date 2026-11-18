## What and why

<!-- What does this change do, and what problem does it solve? -->

## How it was verified

<!-- Tick what you ran. CI runs the unit suite and the manifest check on every pull request. -->

- [ ] `python3 -m unittest discover -s skills/jev/tests` green
- [ ] `claude plugin validate .` clean
- [ ] Version bumped in both `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` (release changes)

## Notes

<!-- Anything reviewers should know: trade-offs, follow-ups. -->
<!-- User-visible change? Add a CHANGELOG.md entry. -->
