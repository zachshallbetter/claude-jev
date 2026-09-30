---
name: jev
description: >-
  Jev (TypeSafe's "System One" decision model) wired into Claude Code and the titan
  household agent: fast typed decisions (choice / score / noul with calibrated
  confidence) for about $0.04 per million input tokens, in ~0.3 s. Use for /jev on|off|status|test|route|sort|ask|calibrate|perms|doctor,
  and whenever the user says "use Jev to sort / triage / classify / route / score these",
  wants a pile of text (emails, tickets, invoices, logs, passages) sorted or flagged, wants
  a cheap guardrail or relevance check in front of an LLM, or wants to add a Jev decision
  step to code in any project (routing, moderation, reranking, extraction, function calling,
  tool-call gating), or wants to check whether Jev's confidence can be trusted (calibration). Jev decides; Claude writes.
---

# /jev: Jev decides, Claude writes

Jev is a hosted decision model. It takes a **state** (text or JSON) and a map of **typed
questions**, and returns typed answers with probabilities. It never generates text, so
there is nothing to hallucinate. It is weak at writing, chat, multi-hop reasoning,
counting, maths and dates. Those stay with Claude or with code.

Everything goes through one stdlib-only script (no installs):

```
J="${CLAUDE_SKILL_DIR}/scripts/jev.py"      # this skill's own folder; run as: python3 "$J" <cmd>
```

## House rules (always)

1. **Jev decides, you write.** Use Jev for the sorting, scoring and routing calls, then do
   all the writing (replies, reports, code) yourself.
2. **Below the review threshold, you make the call.** The threshold is a saved setting:
   `python3 $J status` shows it (0.75 since the 2026-09-25 calibration), and `set threshold`
   changes it. Don't repeat a number from memory. Anything Jev is less sure about goes to a
   "check these" pile that you judge yourself. Don't pass a low-confidence answer along as
   if it were settled.
3. **Anything sent to Jev leaves this machine** (to TypeSafe, directly or via OpenRouter).
   Ask the user before sending private material: personal messages, credentials, health or
   financial records, anything under NDA. `sort` refuses to send without `--yes`. Show the
   user its dry-run estimate first unless they've already approved that pile.
4. **Never handle the API key.** Never ask the user to paste it in chat, never echo it,
   never write it into a file you might share. See Setup.
5. **Don't take claims at face value.** TypeSafe's speed and calibration numbers are their
   own. When a decision matters, spot-check a sample yourself and report what you saw.

## Dispatch: what `/jev <args>` does

| args | do |
|---|---|
| *(none)*, `help` | Run `status`, then show this table in brief. |
| `setup` | Follow **Setup** below. |
| `on` / `off` | `python3 $J on\|off`: the prompt router. It's **OFF by default**. After turning it on, tell the user that every prompt they type now goes to TypeSafe, and that `/jev off` stops it for private work. |
| `status` | `python3 $J status`: switches, provider, calls, cost, tier counts. |
| `test` | `python3 $J test`: the guide's sales-email test. Show the answers, latency and cost. If it fails, show the exact error. |
| `route [msg…]` | `python3 $J route`: dry-runs the router on 10 samples (tiny→hardest plus 2 short replies), or on the given messages. Show the table. |
| `sort <file\|dir> …` | See **Sorting a pile**. |
| `ask …` | `python3 $J ask --state … --questions …` for a one-off decision. |
| `calibrate [set]` | See **Calibration**. Defaults to the bundled `household` set: dry run first, then `--yes --html <file>`, then publish the page. |
| `perms on\|off` | `python3 $J on\|off perms`: the Bash permission gate (see below). Before turning it on, explain what it does and confirm. |
| `skills on\|off` | Turns skill suggestions inside the router on or off. |
| `set <key> <val>` | `threshold`, `perms_threshold`, `tiers.<tier> <model>` |
| `doctor` | `python3 $J doctor`: key, hooks and agents, checked offline. |
| `install` / `uninstall` | Registers or removes the hooks and the four helper agents. Switches stay OFF. |
| `titan …` | See **On titan**. |
| *anything else* (e.g. "/jev on my Projects folder to…", "use Jev to sort these") | Follow **Free-form jobs** below. Don't improvise. |

## Free-form jobs: split the work before reaching for Jev

Most real jobs are mostly *not* Jev. Before sending anything:

1. **Split the job three ways and say so:**
   - **Facts** come from code: git (remotes, owners, dates), the filesystem (sizes, emptiness),
     counts, maths, dates. Never ask Jev a question whose answer is in metadata.
   - **Decisions** go to Jev: judgments over text (what kind, which team, how urgent, is it true).
   - **Writing** is yours: descriptions, replies, reports.
2. **Write the questions** in one file. Every choice question needs an
   `insufficient_information` option (the dry run warns if one is missing). Without it, Jev
   must pick a real option for a near-empty item, often confidently.
3. **Trial new questions:** `sort … --trial 10 --yes`. A question that comes back more than
   half unsure is missing its evidence. Get that fact in code, or add the field that holds it,
   before paying for the full pile.
4. **Dry run, then get consent.** Run without `--yes` and show the user the count, the cost
   and the sample exactly as it will be sent. Use `--redact` (URLs, emails, paths, IPs,
   serial/key-like tokens) and `--max-chars` for anything from someone's files. Send only
   after the user says yes.
5. **Sort** with `--keep-fields --out x.jsonl`. Thin items (under `--min-chars` of real text)
   skip Jev and land in review automatically.
6. **Review the unsure pile yourself**, correct anything you disagree with, then write the
   deliverable using the report convention below.
7. **Save your corrections as calibration data:** `truth x.jsonl --final corrections.json
   --questions … --name <set>`, then `calibrate <set>`. Accuracy is then measured on the
   user's real piles.

For a projects inventory, the facts half already exists:
`python3 ${CLAUDE_SKILL_DIR}/scripts/project_facts.py ~/Projects --out facts.jsonl --forks`
gives git owners, forks, last hand-made commits (skipping automated sweeps), emptiness, a
file-type summary (extension counts and standard project markers, never the folder's own file
names) and ready-to-send text. Then sort with `--questions preset:projects --text-field text`.

## Report convention (every Jev-backed deliverable)

Mark where each decision came from:
- no mark: Jev was sure (at or above the threshold) and you agree
- **†**: Jev was unsure, so you (or the user) decided
- **‡**: Jev was sure, but you overrode it

End with one line in this form:

> Jev decided N, Claude decided M where Jev was unsure (†), Claude overrode K confident answers (‡).

`truth` prints that line for you. Facts from code need no mark, but say where they came from
("dates from git").

## Setup (first run)

1. `python3 $J doctor`. Installed as the **jev plugin**, the plugin already provides the hooks
   and the `jev-{haiku,sonnet,opus,fable}` agents; `python3 $J install` only creates the state
   file. As a user-level skill (`~/.claude/skills/jev`), `install` writes the hooks into
   `~/.claude/settings.json` (with a `.jev-bak` backup) and adds
   `~/.claude/agents/jev-{haiku,sonnet,opus,fable}.md`. Don't have both: the hooks would run twice
   (doctor flags it).
2. **Key.** If doctor says no key, have the user run this in their own terminal. It prompts
   for the key with no echo, so the key never enters chat or shell history:
   ```bash
   security add-generic-password -U -a "$USER" -s jev-openrouter -w
   ```
   Get an OpenRouter key at openrouter.ai/keys (with a little credit), or use a TypeSafe
   direct key from console.typesafe.ai/keys under `-s jev-typesafe`. Environment variables
   also work: `OPENROUTER_API_KEY`, `TYPESAFE_API_KEY` (+ `TYPESAFE_BASE_URL`),
   `JEV_API_KEY` (+ `JEV_BASE_URL`). Off macOS (Linux, cloud sessions) use one of those.
   **Broker mode** keeps the provider key off the machine entirely: `JEV_AUTH=coordinator`,
   `JEV_BASE_URL` = a decision-broker, `JEV_COORDINATOR_KEY_FILE` = an Ed25519 private-key PEM
   whose public half the broker allowlists, and optionally `JEV_COORDINATOR_ID`. In code,
   `decide(..., origin={"source": "user", "person": "miranda", "role": "adult"})` tells a broker
   where a decision came from (it is never sent to a model provider).
3. `python3 $J test`. This makes one real call and shows the answers, latency and cost.

## Level 1: the prompt router (`/jev on`)

A `UserPromptSubmit` hook sends each prompt to Jev in **one fan-out call** that asks three
things: the smallest model tier that can do the job well (tiny/everyday/large/hardest →
haiku/sonnet/opus/fable), whether the prompt is a short reply that only makes sense inside
this conversation, and which installed skill fits best (if any).

**Be honest about the constraint.** Claude Code has no per-message model switch, and a hook
cannot change the model. All the hook can do is add a `[jev-router]` note. When you see one:

- **Tier note:** if the task is self-contained and the named model is smaller than you,
  delegate it with the Agent tool to `jev-<model>`, then relay the result along with the
  helper's closing "done by" line. If the task depends on this conversation's context, or
  you already are that model, do it yourself.
- **Skill note:** load that skill if it actually fits. It's a hint, not an order.
- **No note:** Jev was unsure, slow or off. Carry on normally.

The hook never blocks. It skips slash commands and short replies (under 20 characters or 3
words), times out after 3 s (`JEV_ROUTER_TIMEOUT`), and exits silently on any error.

## Level 2: sorting a pile

```bash
python3 $J presets                      # leads · tickets · invoices
python3 $J sort inbox.jsonl --questions preset:leads \
  --context "We build AI support agents for e-commerce stores" \
  --text-field body --sort-by lead_strength --out /tmp/leads.csv           # dry run first
# …show the estimate, get a yes if the content is private, then add --yes
```

- Input can be `.jsonl`, `.json` (an array), `.csv`, a directory of text files, or `-`
  (stdin). Each row or file becomes one state. Rows run 8 at a time (`--workers`), with
  retries and backoff.
- Custom questions go in `--questions @q.json` as `{key: {type, instructions, criteria}}`.
  Keep questions and thresholds in one file so they're easy to review.
- Every answer gets a `<key>_sure` column and a `decided_by` (`jev` or `review`). Rows where any
  answer falls below the threshold, or whose input is too thin to judge, get `review=true`
  and land in the **check these** pile. You judge those yourself.
- Useful flags:
  - `--redact` and `--max-chars N`: strip identifying details and cap length before anything
    leaves the machine.
  - `--min-chars N` (default 40): route thin items to review without calling Jev.
  - `--keep-fields`: keep each item as sent in the output, so you never have to join results
    back to your data.
  - `--trial N`: test questions on a sample first.
- Afterwards, write the replies or summaries only for the rows that matter (hot leads,
  `today` tickets). Nothing gets paid, rejected or sent on Jev's word alone.

## Calibration (`/jev calibrate`): check the thresholds before trusting them

Every threshold in this skill (the review threshold for route/sort, 0.9 auto-approve) assumes Jev's confidence
means what it says. `calibrate` measures that on labelled data: accuracy by confidence
band, calibration error (ECE), and what each threshold would let through.

```bash
python3 $J calibrate household                                  # dry run: count + cost
python3 $J calibrate household --yes --html /tmp/jev-cal.html --json /tmp/jev-cal.json
```

- The bundled set is `calibration/household.jsonl` + `household.spec.json`: 66 messages,
  12 of them tricky, with hand-written truth. To test your own data, write
  `{"id", "text", "truth": {question: value}, "tags": []}` per line, plus a spec
  `{"name", "description", "context", "questions"}`, and pass
  `calibrate my.jsonl --spec @my.spec.json`. Truth is a choice option, a boolean for a
  noul, or a level index for a score.
- The HTML report has a reliability chart, a threshold slider with review/let-through
  counts, a strip of every answer, a triage board and a table. Publish it with the
  Artifact tool, or open it locally.
- **Repeatability:** `python3 ${CLAUDE_SKILL_DIR}/scripts/jev_stability.py <set> --runs 5 --yes`
  runs a set N times and reports answer flips, threshold crossings and confidence spread by
  band. The 2026-09-26 finding: answers flip on 1–2% of items (all below 0.55), confident
  answers move by 0.01 or less, and only the 0.70–0.85 band crosses the line (a single answer
  at 0.75 has a 4% chance of dipping below it on a rerun, 1% at 0.80, 0% at 0.85). A majority
  vote over reruns scored no better than one run. A different `context` line does change
  answers, so keep it the same between runs you compare.
- Rerun after a model version change, after rewording questions, or before raising
  automation (e.g. turning on `perms`). Report the misses honestly, especially any
  confident ones.
- Baseline (jev-1.13, 2026-09-25, household): category 97% / ECE 0.028, action-today
  94% / ECE 0.085. Every answer at 0.8+ confidence was right except one. Misses
  cluster on "tomorrow" deadlines (a known date weakness) and on a family sender
  talking about an appointment.

## Permission gate (`/jev perms on`, OFF by default)

A `PermissionRequest` hook that only fires when Claude Code is about to show a Bash prompt.
A **static risk list in code is the security boundary**, not Jev. The list covers `rm`,
push/reset, deploys, `railway up`, `ssh`/`rsync`, network writes, `psql`, `launchctl`,
`sudo`, redirects, substitutions, and anything that touches `.env`, secrets or tokens.
Commands on the list are never sent to Jev and always prompt. For everything else, Jev
answers two yes/no questions ("reversible, inside the project" and "serves the task") and
the hook auto-approves only when both reach the `perms_threshold` (0.6 since the history review below). It never denies anything, and the user's
deny rules still win. Dry-run a command with
`python3 $J perm-check "<cmd>" --task "<what you're doing>"`.

**Tuned on real history (2026-09-26, `scripts/perm_tune.py`):** from 52,582 unique commands in
60 days of Claude Code sessions, the risk list blocks most before Jev. Harmless shapes (`2>&1`,
`2>/dev/null`, bare `cd <dir>`, plain assignments) now pass through, so 23% of commands reach Jev
(up from 14%). The review also fixed a list bug: `git checkout -- <file>` was never blocked. It
also added installs (`npm i`, `pnpm install`, `pip install`…) to the list. On 150 sampled commands (133 safe, 17 unsafe, labelled by rules plus
reviewer calls), Jev approved **no unsafe command at any threshold**. The highest unsafe
"reversible" score was 0.29. At 0.6 it approves 41% of safe commands; at the old 0.9 it approved 11%.
Re-tune after big workflow changes: `perm_tune.py sample --n 150 --out s.jsonl`, decide the `?`
rows, then `perm_tune.py run s.jsonl --yes`.

## Building Jev into code (any project)

Read `references/building.md` before writing integration code. It covers the API contract,
question design, the weak spots, and patterns: confidence routing, speculative fan-out,
guardrails, reranking, typed function calling, verified cascades and tool-call gating. The
script is also importable as a library:

```python
import sys; sys.path.insert(0, "${CLAUDE_SKILL_DIR}/scripts")
from jev import decide, sureness, JevError   # decide(state, questions, timeout=, retries=)
```

For production code in a project, prefer the official SDK (`pip install typesafe-sdk`,
`npm i @typesafe-ai/sdk`). Point it at OpenRouter with `TYPESAFE_BASE_URL=https://openrouter.ai/api`.

## On titan (household agent)

`titan-node/scripts/jev_client.py` is a copy of `scripts/jev.py`. `doctor` compares the two
(ignoring the header docstring) and reports DRIFT, so re-copy it whenever you change this file.
The agent gets:
- **`jev_decide` tool**: state plus a questions JSON map, returns a compact typed summary.
  The agent uses it for triage and for picking among candidates.
- **Jev turn router** for `AGENT_TOOL_BRAIN=auto` (`AGENT_JEV_ROUTER=1`): Jev picks
  local Qwen versus Gemini, and only a confident "local" skips Gemini. Recent tool use
  still forces Gemini, and a miss or error falls back to the regex classifier.
- **Key:** `OPENROUTER_API_KEY='…'` (single-quoted) in `agent.env` on the host. Put it
  there over SSH yourself. Never inline it in a command. Follow the `titan-ops` skill:
  preflight before restarting the agent.
