#!/usr/bin/env python3
"""Offline tests for jev.py against a fake System One server. Run: python3 tests/test_jev.py"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

TMP = tempfile.mkdtemp(prefix="jev-test-")
os.environ["JEV_HOME"] = TMP
for k in ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "TYPESAFE_BASE_URL"):
    os.environ.pop(k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import jev  # noqa: E402


class Fake(BaseHTTPRequestHandler):
    requests: list[dict] = []
    responses: list = []          # queue of (status, body) or callables(req) -> (status, body)

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        req = {"path": self.path, "auth": self.headers.get("Authorization"), "body": body}
        Fake.requests.append(req)
        nxt = Fake.responses.pop(0) if Fake.responses else (500, {"error": "no response queued"})
        status, payload = nxt(req) if callable(nxt) else nxt
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def ok(answers, tokens=300, cost=None):
    usage = {"input_tokens": tokens, "output_tokens": 20}
    if cost is not None:
        usage["cost"] = cost
    return (200, {"model": "jev-1.13.0", "answers": answers, "usage": usage})


def router_answers(tier="everyday", conf=0.95, ctx=0.05, skill=None, sconf=0.0):
    a = {"tier": {"type": "choice", "choice": tier, "confidence": conf, "probabilities": {tier: conf}},
         "needs_context": {"type": "noul", "noul": ctx}}
    if skill:
        a["skill"] = {"type": "choice", "choice": skill, "confidence": sconf, "probabilities": {skill: sconf}}
    return a


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        os.environ["JEV_API_KEY"] = "test-key-123"
        os.environ["JEV_BASE_URL"] = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Fake.requests.clear()
        Fake.responses.clear()
        for f in ("state.json", "usage.jsonl"):
            (Path(TMP) / f).unlink(missing_ok=True)
        self.claude = Path(tempfile.mkdtemp(prefix="jev-claude-"))
        (self.claude / "skills").mkdir()
        p = mock.patch.object(jev, "CLAUDE_HOME", self.claude)
        p.start()
        self.addCleanup(p.stop)

    def run_hook(self, fn, payload) -> str:
        out = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), redirect_stdout(out):
            self.assertEqual(fn(), 0)
        return out.getvalue()


class TestDecide(Base):
    def test_request_shape_and_meta(self):
        Fake.responses.append(ok({"u": {"type": "noul", "noul": 0.9}}, tokens=1000))
        r = jev.decide("hello", {"u": {"type": "noul", "instructions": "urgent?"}})
        req = Fake.requests[0]
        self.assertEqual(req["path"], "/v1/systemone")
        self.assertEqual(req["auth"], "Bearer test-key-123")
        self.assertEqual(req["body"]["model"], "jev-1.13.0")        # non-openrouter base → typesafe pin
        self.assertEqual(req["body"]["state"], "hello")
        self.assertAlmostEqual(r["_meta"]["cost_usd"], 1000 * 0.042 / 1e6)

    def test_openrouter_cost_passthrough(self):
        Fake.responses.append(ok({"u": {"type": "noul", "noul": 0.9}}, cost=0.00003))
        self.assertEqual(jev.decide("x", {"u": {"type": "noul", "instructions": "q"}})["_meta"]["cost_usd"], 0.00003)

    def test_retries_overload_then_succeeds(self):
        Fake.responses += [(529, {"error": "overloaded"}), (429, {"error": "slow down"}),
                           ok({"u": {"type": "noul", "noul": 0.1}})]
        r = jev.decide("x", {"u": {"type": "noul", "instructions": "q"}}, retries=2)
        self.assertEqual(len(Fake.requests), 3)
        self.assertEqual(r["answers"]["u"]["noul"], 0.1)

    def test_auth_error_not_retried(self):
        Fake.responses += [(401, {"error": "bad key"}), ok({})]
        with self.assertRaises(jev.JevError) as cm:
            jev.decide("x", {"u": {"type": "noul", "instructions": "q"}}, retries=3)
        self.assertEqual(cm.exception.status, 401)
        self.assertEqual(len(Fake.requests), 1)

    def test_usage_log_has_no_content_or_key(self):
        Fake.responses.append(ok({"u": {"type": "noul", "noul": 0.9}}))
        jev.decide("SECRET-CONTENT", {"u": {"type": "noul", "instructions": "q"}})
        log = (Path(TMP) / "usage.jsonl").read_text()
        self.assertNotIn("SECRET-CONTENT", log)
        self.assertNotIn("test-key-123", log)

    def test_sureness(self):
        self.assertAlmostEqual(jev.sureness({"type": "noul", "noul": 0.2}), 0.8)
        self.assertEqual(jev.sureness({"type": "choice", "confidence": 0.7}), 0.7)


class TestRouterHook(Base):
    def test_off_is_silent_and_offline(self):
        out = self.run_hook(jev.hook_prompt, {"prompt": "please write a long report on vector databases"})
        self.assertEqual(out, "")
        self.assertEqual(Fake.requests, [])

    def test_on_emits_tier_note(self):
        jev.save_state({**jev.load_state(), "router": True})
        Fake.responses.append(ok(router_answers("large", 0.93)))
        out = self.run_hook(jev.hook_prompt, {"prompt": "build a CLI that ingests PDFs and writes a CSV report"})
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("LARGE → opus", ctx)
        self.assertIn("jev-opus", ctx)

    def test_trivial_prompts_skip(self):
        jev.save_state({**jev.load_state(), "router": True})
        for p in ("/jev status", "yes", "ok go ahead", "<command-name>x</command-name> long enough text here"):
            self.assertEqual(self.run_hook(jev.hook_prompt, {"prompt": p}), "")
        self.assertEqual(Fake.requests, [])

    def test_low_confidence_or_followup_gives_no_tier_note(self):
        jev.save_state({**jev.load_state(), "router": True})
        Fake.responses += [ok(router_answers("tiny", 0.41)), ok(router_answers("tiny", 0.99, ctx=0.9))]
        for _ in range(2):
            self.assertEqual(self.run_hook(jev.hook_prompt, {"prompt": "yes do that but make it much shorter please"}), "")

    def test_failure_is_silent(self):
        jev.save_state({**jev.load_state(), "router": True})
        Fake.responses.append((500, {"error": "boom"}))
        self.assertEqual(self.run_hook(jev.hook_prompt, {"prompt": "write a proposal for the new onboarding flow"}), "")

    def test_skill_catalog_and_skill_note(self):
        sk = self.claude / "skills" / "titan-ops"
        sk.mkdir()
        (sk / "SKILL.md").write_text("---\nname: titan-ops\ndescription: >-\n  Operate titan-node, the GPU host.\n"
                                     "  More detail here.\n---\nbody\n")
        off = self.claude / "skills" / "medium"
        off.mkdir()
        (off / "SKILL.md").write_text("---\nname: medium\ndescription: Post to Medium.\n---\n")
        (self.claude / "settings.json").write_text(json.dumps({"skillOverrides": {"medium": "off"}}))
        cat = jev.skill_catalog()
        self.assertEqual(cat, {"titan-ops": "Operate titan-node, the GPU host."})
        jev.save_state({**jev.load_state(), "router": True})
        Fake.responses.append(ok(router_answers("everyday", 0.9, skill="titan-ops", sconf=0.8)))
        out = self.run_hook(jev.hook_prompt, {"prompt": "is the fleet healthy on the gpu box right now?"})
        self.assertIn("`titan-ops`", out)
        self.assertIn("none", Fake.requests[0]["body"]["questions"]["skill"]["criteria"])


class TestPermissionGate(Base):
    RISKY = ["rm -rf build", "rm file.txt", "git push origin main", "git status && git push", "sudo ls",
             "/usr/bin/sudo ls", "FOO=1 sudo ls", "cat .env", "echo $(whoami)", "ls > out.txt",
             "npx wrangler deploy", "ssh titan uptime", "railway up", "bash -c 'ls'", ". ./x.sh",
             "curl -X POST https://x", "psql -c 'drop table x'", "python3 -c 'print(1)'",
             "git reset --hard HEAD~1", "launchctl unload x", "cat ~/.ssh/id_rsa", "kill -9 1",
             "git checkout -- src/file.ts", "git reset -q && git checkout -- .agents/lock.json 2>/dev/null",
             "git checkout .", "pnpm install --silent >/dev/null 2>&1", "npm i left-pad", "pip install requests",
             "cd /p && echo hi > out.txt", 'X="$(whoami)" && ls', 'cd "$(git rev-parse --show-toplevel)"',
             "ls 2>/dev/null; rm -rf build", 'S=/tmp/x; rm "$S"',
             "curl -s -H 'Authorization: Bearer abcdef0123456789abcdef' https://api.example.com/v1/me",
             "echo sk-or-v1-0123456789abcdef0123456789abcdef | pbcopy",
             "git remote set-url origin https://ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345@github.com/x/y",
             "grep -r AKIAABCDEFGHIJKLMNOP .", "echo eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig",
             "printf '%s' 0123456789abcdef0123456789abcdef01"]
    ROUTINE = ["ls src", "git status", "git diff --stat", "bun test src/utils/date.test.ts", "npm test",
               "cat package.json", "python3 scripts/test_x.py", "grep -rn foo src | head -20",
               'cd "/Users/z/Projects/My App" && git status', "ls missing 2>/dev/null", "npm test 2>&1 | tail -20",
               'S=/private/tmp/scratch; ls "$S"', "cd $HOME/Projects/x && git log -3", "git checkout -b feature/x"]

    def test_static_list(self):
        for c in self.RISKY:
            self.assertTrue(jev.never_auto_approve(c), c)
        for c in self.ROUTINE:
            self.assertFalse(jev.never_auto_approve(c), c)

    def test_hook_allows_only_when_both_clear(self):
        jev.save_state({**jev.load_state(), "perms": True})
        payload = {"tool_name": "Bash", "cwd": "/p", "tool_input": {"command": "npm test", "description": "Run tests"}}
        Fake.responses.append(ok({"reversible": {"type": "noul", "noul": 0.95},
                                  "serves_task": {"type": "noul", "noul": 0.93}}))
        out = self.run_hook(jev.hook_permission, payload)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["decision"]["behavior"], "allow")
        Fake.responses.append(ok({"reversible": {"type": "noul", "noul": 0.95},
                                  "serves_task": {"type": "noul", "noul": 0.5}}))
        self.assertEqual(self.run_hook(jev.hook_permission, payload), "")

    def test_hook_risky_never_reaches_jev(self):
        jev.save_state({**jev.load_state(), "perms": True})
        out = self.run_hook(jev.hook_permission, {"tool_name": "Bash", "cwd": "/p",
                                                  "tool_input": {"command": "git push --force"}})
        self.assertEqual(out, "")
        self.assertEqual(Fake.requests, [])

    def test_hook_off_and_non_bash_silent(self):
        self.assertEqual(self.run_hook(jev.hook_permission, {"tool_name": "Bash", "tool_input": {"command": "ls"}}), "")
        jev.save_state({**jev.load_state(), "perms": True})
        self.assertEqual(self.run_hook(jev.hook_permission, {"tool_name": "Write", "tool_input": {}}), "")
        self.assertEqual(Fake.requests, [])


class TestSortAndInstall(Base):
    def test_sort_flags_unsure(self):
        def respond(req):
            item = req["body"]["state"]["item"]
            conf = 0.95 if "budget" in item else 0.4
            return ok({"kind": {"type": "choice", "choice": "new_lead", "confidence": conf},
                       "reply": {"type": "noul", "noul": 0.9}})
        Fake.responses += [respond, respond]
        rows = jev.sort_pile([("1", "we have budget"), ("2", "hmm maybe")],
                             {"kind": {"type": "choice", "instructions": "k", "criteria": {"new_lead": None}},
                              "reply": {"type": "noul", "instructions": "r"}},
                             context="we sell X", threshold=0.6, workers=1)
        by = {r["id"]: r for r in rows}
        self.assertFalse(by["1"]["review"])
        self.assertEqual(by["2"]["unsure"], ["kind"])

    def test_sort_requires_yes(self):
        f = Path(TMP) / "pile.jsonl"
        f.write_text('{"id": "a", "body": "hi"}\n')
        with redirect_stdout(io.StringIO()):
            rc = jev.main(["sort", str(f), "--questions", "preset:leads", "--text-field", "body"])
        self.assertEqual(rc, 2)
        self.assertEqual(Fake.requests, [])

    def test_install_idempotent_and_uninstall_clean(self):
        (self.claude / "settings.json").write_text(json.dumps({"permissions": {"allow": ["Bash(npm:*)"]}}))
        first = jev.install()
        self.assertIn("hook UserPromptSubmit", first)
        self.assertIn("hook.py prompt", json.loads((self.claude / "settings.json").read_text())
                      ["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"])
        self.assertEqual(jev.install(), [])
        s = json.loads((self.claude / "settings.json").read_text())
        self.assertEqual(s["permissions"]["allow"], ["Bash(npm:*)"])
        self.assertEqual(s["hooks"]["PermissionRequest"][0]["matcher"], "Bash")
        self.assertTrue((self.claude / "agents" / "jev-fable.md").read_text().count("model: fable"))
        jev.uninstall()
        s = json.loads((self.claude / "settings.json").read_text())
        self.assertNotIn("hooks", s)
        self.assertFalse((self.claude / "agents" / "jev-haiku.md").exists())

    def test_calibrate_grades_and_bins(self):
        def respond(req):
            text = req["body"]["state"]["item"]
            wrong = "dad" in text
            return ok({"category": {"type": "choice", "choice": "appointment" if wrong else "family", "confidence": 0.92},
                       "action_today": {"type": "noul", "noul": 0.2}})
        Fake.responses += [respond, respond]
        rows = [{"id": "1", "text": "mom dinner", "truth": {"category": "family", "action_today": False}},
                {"id": "2", "text": "dad dentist tomorrow", "truth": {"category": "family", "action_today": True}, "tags": ["tricky"]}]
        spec = {"name": "t", "context": "household", "questions": {
            "category": {"type": "choice", "instructions": "k", "criteria": {"family": None, "appointment": None}},
            "action_today": {"type": "noul", "instructions": "today"}}}
        res = jev.calibrate(rows, spec, workers=1)
        self.assertEqual(res["stats"]["category"]["accuracy"], 0.5)
        self.assertEqual(res["stats"]["action_today"]["accuracy"], 0.5)
        self.assertEqual(res["stats"]["category"]["bins"][0]["n"], 2)
        a = next(it for it in res["items"] if it["id"] == "2")["answers"]["action_today"]
        self.assertEqual((a["pred"], a["truth"], a["correct"], a["sure"]), (False, True, False, 0.8))
        out = Path(TMP) / "cal.html"
        jev.render_calibration(res, out)
        html = out.read_text()
        self.assertNotIn("/*__CAL_DATA__*/null", html)
        self.assertIn('"accuracy": 0.5', html)

    def test_reslice_scores_subset_without_calls(self):
        items = [{"id": str(i), "text": "t", "tags": [tag], "cost_usd": 0.0,
                  "answers": {"kind": {"pred": "a", "truth": "a" if ok else "b", "sure": s, "correct": ok}}}
                 for i, (tag, ok, s) in enumerate([("agreed", True, 0.99)] * 6 + [("reviewer-call", False, 0.6),
                                                   ("reviewer-call", True, 0.7), ("corrected", False, 0.9)])]
        res = {"meta": {"name": "p", "run_at": "x"}, "threshold": 0.75,
               "questions": {"kind": {"type": "choice"}}, "items": items}
        sub = jev.reslice(res, ["reviewer-call", "corrected"])
        self.assertEqual(sub["meta"]["items"], 3)
        self.assertAlmostEqual(sub["stats"]["kind"]["accuracy"], 1 / 3, places=3)
        self.assertEqual(sub["by_tag"]["corrected"]["kind"]["confident_wrong"], 1)
        self.assertNotIn("agreed", sub["by_tag"])
        self.assertEqual(Fake.requests, [])

    def test_bundled_calibration_set_valid(self):
        spec = json.loads((jev.SKILL_DIR / "calibration" / "household.spec.json").read_text())
        opts = set(spec["questions"]["category"]["criteria"])
        rows = [json.loads(l) for l in (jev.SKILL_DIR / "calibration" / "household.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 66)
        for r in rows:
            self.assertIn(r["truth"]["category"], opts, r["id"])
            self.assertIsInstance(r["truth"]["action_today"], bool)

    def test_threshold_single_source(self):
        self.assertEqual(jev.DEFAULT_STATE["threshold"], jev.REVIEW_THRESHOLD)
        (Path(TMP) / "state.json").write_text("{}")               # a state file without the key
        self.assertEqual(jev.load_state()["threshold"], jev.REVIEW_THRESHOLD)
        src = (jev.SKILL_DIR / "scripts" / "jev.py").read_text()
        self.assertNotRegex(src, r'get\("threshold", 0\.\d+\)')   # no literal fallbacks

    def test_redact(self):
        out = jev.redact("see https://x.io/a, mail a@b.co, /Users/zach/p/f.txt ../x/y.md SN4829XK33ZQ91 10.0.0.9 ok", 200)
        for leaked in ("x.io", "a@b.co", "/Users/", "../x", "SN4829", "10.0.0.9"):
            self.assertNotIn(leaked, out)
        self.assertIn("ok", out)
        for kept in ("3d-floating-head", "character-carousel-demo", "v0.5.3", "2026-09-25"):
            self.assertIn(kept, jev.redact(kept))
        self.assertEqual(jev.redact("sk-or-v1-0123456789abcdef0123456789abcdef"), "[id]")
        self.assertEqual(jev.redact({"a": ["x" * 50]}, 10), {"a": ["x" * 10]})

    def test_thin_items_skip_jev(self):
        Fake.responses.append(ok({"kind": {"type": "choice", "choice": "app", "confidence": 0.95}}))
        rows = jev.sort_pile([("empty", "Folder: X"), ("full", "A long enough description of a web app with a UI.")],
                             {"kind": {"type": "choice", "instructions": "k", "criteria": {"app": None}}},
                             context=None, threshold=0.75, workers=1, min_chars=20, keep_fields=True)
        by = {r["id"]: r for r in rows}
        self.assertEqual(len(Fake.requests), 1)
        self.assertTrue(by["empty"]["thin"] and by["empty"]["review"])
        self.assertEqual(by["empty"]["decided_by"], "review")
        self.assertEqual((by["full"]["kind"], by["full"]["decided_by"]), ("app", "jev"))
        self.assertIn("web app", by["full"]["input"])

    def test_thin_bar_ignores_preset_labels(self):
        ign = json.loads((jev.SKILL_DIR / "presets" / "projects.json").read_text())["thin_ignore"]
        empty = "Folder: RoamRide\nTop-level entries (excluding hidden): 0\nREADME: none"
        self.assertGreater(jev.text_size(empty), 60)            # labels alone would clear the bar
        self.assertEqual(jev.content_size(empty, ign), 0)       # but there is no real description
        full = "Folder: x\nTop-level entries (excluding hidden): 4\nREADME excerpt: " + "a real description " * 4
        self.assertGreaterEqual(jev.content_size(full, ign), 60)

    def test_contents_summary_types_not_names(self):
        sys.path.insert(0, str(jev.SKILL_DIR / "scripts"))
        import project_facts as pf
        d = Path(tempfile.mkdtemp(prefix="jev-proj-"))
        (d / "src").mkdir(); (d / "node_modules" / "x").mkdir(parents=True)
        (d / "package.json").write_text("{}"); (d / "src" / "secret-plan.ts").write_text("x")
        (d / "src" / "b.ts").write_text("x"); (d / "node_modules" / "x" / "dep.js").write_text("x")
        (d / "child").mkdir(); (d / "child" / "Cargo.toml").write_text("")
        line = pf.contents_line(pf.contents_summary(d))
        self.assertIn("2 .ts", line)
        self.assertIn("package.json", line)                  # standard marker
        self.assertIn("src/", line)
        self.assertIn("1 sub-project", line)
        self.assertNotIn("secret-plan", line)                # never the folder's own file names
        self.assertNotRegex(line, r"\d \.js\b")               # dependency dirs skipped (.json is fine)
        empty = Path(tempfile.mkdtemp(prefix="jev-empty-"))
        self.assertEqual(pf.contents_line(pf.contents_summary(empty)), "Contents: none")

    def test_sweep_detection_and_dates(self):
        sys.path.insert(0, str(jev.SKILL_DIR / "scripts"))
        import project_facts as pf
        import subprocess as sp
        root = Path(tempfile.mkdtemp(prefix="jev-repos-"))
        def commit(repo, msg, date):
            env = {**os.environ, "GIT_AUTHOR_DATE": date + "T12:00:00", "GIT_COMMITTER_DATE": "2026-09-25T12:00:00"}
            (repo / "f").write_text(msg + date)
            sp.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True, env=env)
            sp.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", msg],
                   check=True, capture_output=True, env=env)
        for i in range(5):
            r = root / f"r{i}"; r.mkdir(); sp.run(["git", "init", "-q", str(r)], check=True)
            if i == 0:
                commit(r, "real work on the parser (#12)", "2026-08-01")
            commit(r, f"chore: nightly sweep {i} (auto 2026-09-0{i + 1})", "2026-09-10")
        rows = {x["id"]: x for x in pf.collect(root, [])}
        self.assertIn(pf.normalize_subject("chore: nightly sweep 3 (auto 2026-09-04)"), pf._SWEEPS)
        self.assertEqual(rows["r0"]["last_hand_commit"], "2026-08-01")   # author date, sweeps skipped
        self.assertEqual(rows["r0"]["last_commit"], "2026-09-10")
        self.assertIsNone(rows["r1"]["last_hand_commit"])                 # only sweep commits

    def test_lint_wants_insufficient_option(self):
        self.assertTrue(jev.lint_questions({"k": {"type": "choice", "criteria": {"a": None, "b": None}}}))
        self.assertFalse(jev.lint_questions({"k": {"type": "choice", "criteria": {"a": None, "insufficient_information": None}}}))

    def test_trial_flags_unanswerable_question(self):
        f = Path(TMP) / "pile.jsonl"
        f.write_text("".join(json.dumps({"id": str(i), "t": f"item number {i} with plenty of text in it"}) + "\n" for i in range(5)))
        Fake.responses += [ok({"owner": {"type": "choice", "choice": "me", "confidence": 0.3}})] * 3
        out = io.StringIO()
        with redirect_stdout(out):
            rc = jev.main(["sort", str(f), "--text-field", "t", "--trial", "3", "--yes", "--workers", "1",
                           "--questions", json.dumps({"owner": {"type": "choice", "instructions": "whose?",
                                                               "criteria": {"me": None, "them": None}}})])
        self.assertEqual(rc, 0)
        self.assertEqual(len(Fake.requests), 3)
        self.assertIn("100% unsure", out.getvalue())
        self.assertIn("evidence is probably not in the input", out.getvalue())

    def test_dry_run_shows_redacted_sample(self):
        f = Path(TMP) / "pile2.jsonl"
        f.write_text(json.dumps({"id": "1", "t": "Contact https://secret.example/x now about the photo-editing app and its plugin system"}) + "\n"
                     + json.dumps({"id": "2", "t": ""}) + "\n")
        out = io.StringIO()
        with redirect_stdout(out):
            rc = jev.main(["sort", str(f), "--text-field", "t", "--redact", "--min-chars", "20", "--questions", "preset:projects"])
        self.assertEqual(rc, 2)
        self.assertEqual(Fake.requests, [])
        self.assertNotIn("secret.example", out.getvalue())
        self.assertIn("[url]", out.getvalue())
        self.assertIn("1 thin item", out.getvalue())

    def test_truth_tags_and_decision_line(self):
        q = {"kind": {"type": "choice", "instructions": "k", "criteria": {"app": None, "tool": None}}}
        srows = [{"id": "a", "input": "x", "kind": "app", "kind_sure": 0.95},
                 {"id": "b", "input": "y", "kind": "app", "kind_sure": 0.95},
                 {"id": "c", "input": {"f": 1}, "kind": "tool", "kind_sure": 0.4}]
        rows, counts = jev.build_truth(srows, {"b": {"kind": "tool"}, "c": {"kind": "app"}}, q, 0.75)
        tags = {r["id"]: r["tags"][0] for r in rows}
        self.assertEqual(tags, {"a": "agreed", "b": "corrected", "c": "reviewer-call"})
        self.assertEqual(next(r for r in rows if r["id"] == "b")["truth"]["kind"], "tool")
        self.assertIn("Jev decided 1, Claude decided 1 where Jev was unsure (†), Claude overrode 1", jev.decision_line(counts))
        with self.assertRaises(jev.JevError):
            jev.build_truth([{"id": "z", "kind": "app"}], {}, q, 0.75)

    def test_titan_copy_drift(self):
        me = (jev.SKILL_DIR / "scripts" / "jev.py").read_text()
        copy = Path(TMP) / "jev_client.py"
        copy.write_text(me.replace('"""jev —', '"""jev —\n\nCOPY header note.', 1))
        with mock.patch.dict(os.environ, {"JEV_TITAN_COPY": str(copy)}):
            self.assertEqual(jev.titan_copy_status()[0], "in sync")
            copy.write_text(copy.read_text() + "\n# drift\n")
            self.assertEqual(jev.titan_copy_status()[0], "DRIFT")

    def test_presets_valid(self):
        for name, p in jev._presets().items():
            spec = json.loads(p.read_text())
            for k, q in spec["questions"].items():
                self.assertIn(q["type"], ("noul", "choice", "score"), f"{name}.{k}")
                if q["type"] == "score":
                    self.assertTrue(2 <= len(q["criteria"]) <= 10)


if __name__ == "__main__":
    unittest.main(verbosity=1)


class CoordinatorModeTests(unittest.TestCase):
    """JEV_AUTH=coordinator: no Jev key; each call signs a fresh EdDSA token for the decision-broker."""

    def test_mint_and_verify(self):
        import base64, json, tempfile
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        key = Ed25519PrivateKey.generate()
        with tempfile.NamedTemporaryFile("wb", suffix=".pem", delete=False) as fh:
            fh.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
        env = {"JEV_AUTH": "coordinator", "JEV_BASE_URL": "http://broker.invalid/", "JEV_COORDINATOR_KEY_FILE": fh.name,
               "JEV_COORDINATOR_ID": "unit-test"}
        with mock.patch.dict(os.environ, env, clear=False):
            creds = jev.resolve_credentials()
        self.assertEqual(creds["provider"], "broker")
        self.assertEqual(creds["base"], "http://broker.invalid")
        token = jev._bearer(creds)
        head, body, sig = token.split(".")
        pad = lambda s: s + "=" * (-len(s) % 4)
        key.public_key().verify(base64.urlsafe_b64decode(pad(sig)), f"{head}.{body}".encode())
        claims = json.loads(base64.urlsafe_b64decode(pad(body)))
        self.assertEqual((claims["sub"], claims["type"]), ("unit-test", "coordinator"))
        self.assertGreater(claims["exp"], claims["iat"])

    def test_missing_settings_or_key_raise_jev_error(self):
        with mock.patch.dict(os.environ, {"JEV_AUTH": "coordinator", "JEV_BASE_URL": "", "JEV_COORDINATOR_KEY_FILE": ""}):
            with self.assertRaises(jev.JevError):
                jev.resolve_credentials()
        with self.assertRaises(jev.JevError):
            jev._bearer({"provider": "broker", "key_file": "/nonexistent.pem", "sub": "x"})
