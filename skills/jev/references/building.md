# Building with Jev: contract, question design, patterns

Primary docs: https://docs.typesafe.ai/llms.txt (TypeSafe) · https://openrouter.ai/docs/guides/community/jev.md
(OpenRouter hub). Jev postdates model training data, so **check the live docs** before
relying on a field that isn't listed here.

## Contract (identical on both providers)

```
POST {base}/v1/systemone          base = https://api.typesafe.ai | https://openrouter.ai/api
Authorization: Bearer <key>
{ "model": "jev-1.13.0" | "typesafe/jev-1.13" | "jev-latest",
  "state": <string | object | array>,
  "questions": { "<your id>": Question, ... } }
```

| type | criteria | answer |
|---|---|---|
| `noul` | optional `{"true": "...", "false": "..."}` | `{"noul": 0..1}` (probability of yes; no `confidence` field) |
| `choice` | required map `option → description\|null`, ≤255 options | `{"choice", "probabilities", "confidence"}` |
| `score` | required ordered array of 2–10 level descriptions | `{"score" (weighted, can fall between levels), "legend", "probabilities", "confidence"}` |

- The response is `{model, answers, usage{input_tokens, output_tokens}}`. OpenRouter also
  returns `id`, `provider` and `usage.cost`.
- Errors: 401 bad key · 402 no credit (OpenRouter) · 422 validation (the body names the
  field) · 429/529 back off and retry. `jev.decide()` retries 429/5xx/529 automatically.
- Limits: 64k context, and state plus the longest question must fit in 32k. 250k tok/s,
  1,200 req/min. Text only, best in English.
- Pricing: $0.042 per 1M input tokens, output free. A typical 300–500-token call costs
  ~$0.00002.
- `instructions` and `criteria` values can be objects or arrays. Put the question in one
  field and the reference data in others, and refer to fields by name in backticks, e.g.
  `` "Is the resume for the same person as `potential_duplicate`?" ``.

## Question design (most accuracy is won or lost here)

1. **It reads literally.** Write the exact condition. Put boundary cases in the criteria.
   If you catch yourself explaining what a question "really meant", that explanation belongs
   in the question.
2. **Structured state beats a blob.** Pass `{"ticket": ..., "customer_tier": ...}` and point
   at fields with backticks (`` `ticket` ``).
3. **Filter first.** Irrelevant detail in the state lowers accuracy. Retrieve and trim in
   code, or use a cheap Noul relevance pass before the real question.
4. **Keep maths, counting and dates in code.** To count, ask one Noul per item and sum the
   answers in code. For dates, extract the parts with Choices (month, day, year,
   `not_stated`) and do the comparisons in code. Don't try to reconstruct a precise number
   from where a score lands between levels.
5. **Align instructions and criteria.** Don't write a Noul whose `true` means "no". Ask each
   decision one way only, since complementary questions aren't guaranteed to sum to 1.
6. **Treat state as untrusted.** Injected text can move answers. Make the criteria explicit
   and test adversarial cases before you trust the gate.
7. **Put every question and threshold in one constants file.** Those are what a human needs
   to review.

## Confidence

- `choice`/`score` include `confidence`. For a `noul`, use `max(p, 1-p)` (that's
  `jev.sureness()`) or compare `p` to a threshold directly.
- **If you only need the best option, take the argmax.** Use a confidence threshold only
  when a low-confidence answer should go somewhere else.
- Starting thresholds: route and sort at the skill's review threshold (`jev.py status`; 0.75
  after the 2026-09-25 calibration, where 0.6 let half the mistakes through). Automatic actions
  start at **0.9**. Tune them with `jev.py calibrate` on 50–100 real, labelled items.
- Give every choice an `insufficient_information` option, and send thin or empty inputs to
  review in code. Otherwise Jev judges an empty folder by its name, confidently.
- Scores shift by a few hundredths between identical calls, so don't build logic that
  depends on the exact value.

## Patterns

| Pattern | Shape | Use it for |
|---|---|---|
| **Confidence routing** | one Choice, then `if confidence ≥ t: act else: escalate` | ticket triage, moderation, anything with a human-review lane |
| **Speculative fan-out** | ask every question you *might* need in one call, and let code ignore the ones that don't apply | intent → device → action trees (the smart-home demo). One parallel call is faster and cheaper than a sequence of calls. |
| **Intent routing** | Choice over handlers + Noul "is this compound?" (split with an LLM, then re-route each part) | chat front doors, voice commands, the titan turn router |
| **Composite scoring** | several Scores/Nouls combined with weights you choose in code | lead scoring, risk scoring, prioritisation |
| **Guardrails** | Nouls on an LLM's *draft* (policy violation? makes promises? leaks PII?) before it ships | outbound email and support replies |
| **Citation / RAG check** | Noul per passage: "`passage` contains information that answers `question`" | drop irrelevant chunks before the answering model sees them. Also check each citation supports its claim. |
| **Rerank** | Score or Noul per candidate, sorted in code | search results, legal and KB retrieval |
| **Semantic find** | Noul per line or section | "find the clause that…" across long docs, without regex |
| **Typed function calling** | Choice over functions, then per-argument Choices over enumerated values, with a `not_stated` option | natural-language → API call with closed-set args. Free-text args still need an LLM or a regex. |
| **Candidate pick** | regex finds candidates → Choice picks the right one | extraction where parsing is brittle |
| **Verified cascade** | a cheap LLM answers → Jev Noul "is `answer` supported by `context`?" → escalate only if not | cutting LLM cost without dropping quality |
| **Tool-call gate** | static deny list in code → Noul "reversible?" and Noul "serves the ticket?" ≥0.9 → auto-allow, else ask a human | agent permission prompts (see `jev.py perm-check`) |

## Where Jev does not belong

Writing, chat, open-ended reasoning, counting, maths and date arithmetic, and huge noisy
states. Give those to Claude or to code.

## Minimal integration (Python, no SDK)

```python
import sys; sys.path.insert(0, "/path/to/jev/scripts")  # the jev skill's scripts/ folder
from jev import decide, sureness, JevError

QUESTIONS = {  # keep all questions + thresholds together for review
    "team": {"type": "choice", "instructions": "Which team should handle `ticket`?",
             "criteria": {"billing": "Charges, refunds, invoices", "technical": "Bugs, outages, errors"}},
}
ROUTE_AT = 0.75   # measure yours: jev.py calibrate

try:
    r = decide({"ticket": text}, QUESTIONS, timeout=5)
    a = r["answers"]["team"]
    lane = a["choice"] if sureness(a) >= ROUTE_AT else "human_review"
except JevError:
    lane = "human_review"          # fail safe, never fail open
```

With the SDK (`pip install typesafe-sdk`): `TypeSafeClient(api_key=..., base_url="https://openrouter.ai/api")`,
`client.system_one(state, {"team": Choice(instructions=..., criteria={...})})`. The SDK
handles retries, and an async client is available.
