from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import io
import json
import os
from pathlib import Path
import subprocess
import unittest

from helpers import ROOT, LifeOS, episode, raw_conversation

import anchor
from anchor_core import extract, inbox, service, weekly
from anchor_core.store import TZ, AnchorError, resolve_repo


def run(life, *argv, today="2026-10-26"):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = anchor.main(["--repo", str(life.repo), "--today", today, "--json", *argv])
        except SystemExit as exit_:
            code = exit_.code
    text = out.getvalue()
    return code, (json.loads(text) if text.strip().startswith(("{", "[")) else text), err.getvalue()


class FlowTest(unittest.TestCase):
    def setUp(self):
        self.life = LifeOS()

    def tearDown(self):
        self.life.close()

    def test_now_act_fact_weekly(self):
        code, data, _ = run(self.life, "now", "--trigger", "她说想自己待一会", "--thought", "她是不是要走了",
                            "--body", "胸口发紧", "--certainty", "70", "--urge", "8", "--conditions", "半夜,电话")
        self.assertEqual(code, 0)
        identity = data["episode"]["id"]
        self.assertEqual(identity, "ep-2026-10-26-01")
        self.assertEqual(data["episode"]["script_used"], "好，你先休息。")
        self.assertLessEqual(len(data["reply"]), 5)
        self.assertTrue(any(line.startswith("现在去做：") for line in data["reply"]))
        self.assertFalse(any("她不会" in line for line in data["reply"]))

        code, data, _ = run(self.life, "act", identity, "--action", "said_ok", "--miss", "no")
        self.assertEqual((code, data["episode"]["action"]), (0, "said_ok"))

        code, data, _ = run(self.life, "due", today="2026-10-28")
        self.assertEqual([item["id"] for item in data["due"]], [identity])

        code, data, _ = run(self.life, "fact", identity, "--outcome", "not_happened", "--fact", "她说没事",
                            "--recovery-minutes", "25")
        self.assertEqual(data["episode"]["outcome"], "unverifiable")
        code, data, _ = run(self.life, "fact", identity, "--outcome", "not_happened",
                            "--fact", "第二天中午她约我吃饭", "--recovery-minutes", "25")
        self.assertEqual(data["episode"]["outcome"], "not_happened")

        code, data, _ = run(self.life, "weekly", "--week", "2026-44", "--write")
        self.assertEqual(code, 0)
        metrics = data["metrics"]
        self.assertEqual((metrics["episodes"], metrics["no_check_rate"], metrics["execution_rate"]), (1, 1.0, 1.0))
        report = (self.life.paths.weekly / "2026-44.md").read_text(encoding="utf-8")
        for part in ("未确认率", "执行率", "校准", "给咨询师的话", "updated: 2026-10-26"):
            self.assertIn(part, report)

    def test_status_drill_view_ladder(self):
        code, data, _ = run(self.life, "status")
        self.assertEqual((code, data["view"], data["rung"]), (0, "V01", "L01"))
        code, data, _ = run(self.life, "drill", "--hot")
        self.assertEqual((data["scene"], data["view"]), ("sc-2026-08-28-01", "V01"))
        code, data, _ = run(self.life, "drill", "log", "--scene", "sc-2026-08-28-01", "--view", "V01",
                            "--suds-before", "60", "--suds-after", "35", "--within-3s", "yes", "--verbatim", "yes",
                            "--held", "no")
        self.assertTrue(data["added"])
        code, data, _ = run(self.life, "view")
        self.assertIsNone(data["view"])
        code, data, _ = run(self.life, "ladder", "done", "L01", "--suds", "30")
        code, data, _ = run(self.life, "ladder", "done", "L01", "--suds", "20")
        self.assertEqual((data["cleared"], data["next"]), (True, "L02"))
        code, data, _ = run(self.life, "validate")
        self.assertEqual((code, data["errors"]), (0, []))

    def test_drill_plan_writes_knowledge_files(self):
        code, data, _ = run(self.life, "drill", "plan", "--days", "3", "--hot-days", "2")
        self.assertEqual(len(data["written"]), 3)
        second = (self.life.repo / data["written"][1]).read_text(encoding="utf-8")
        self.assertTrue(second.startswith("---\nname: 演练稿 2026-10-27"))
        self.assertIn("hot: true", second)

    def test_narration_for_tts(self):
        target = self.life.repo / "drill.txt"
        code, data, _ = run(self.life, "drill", "--narration", str(target), "--say-markup")
        text = target.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn("[[slnc 30000]]", text)
        self.assertIn("对方说：我想自己待一会。", text)
        self.assertNotIn("**", text)

    def test_init_creates_only_missing_files(self):
        (self.life.paths.area / "views.md").write_text("keep", encoding="utf-8")
        self.life.paths.episodes.unlink()
        code, data, _ = run(self.life, "init")
        self.assertEqual(code, 0)
        self.assertIn("areas/relationship/inbox.md", data["created"])
        self.assertIn("areas/relationship/episodes.jsonl", data["created"])
        self.assertEqual((self.life.paths.area / "views.md").read_text(encoding="utf-8"), "keep")
        self.assertTrue(self.life.paths.weekly.is_dir())

    def test_unknown_episode_is_reported(self):
        code, _, err = run(self.life, "fact", "ep-2026-01-01-01", "--outcome", "unverifiable")
        self.assertEqual(code, 2)
        self.assertIn("episode_not_found", err)


class InboxTest(unittest.TestCase):
    def setUp(self):
        self.life = LifeOS()

    def tearDown(self):
        self.life.close()

    def test_ingest_applies_ops_and_keeps_failures(self):
        ops = [
            {"op": "episode", "id": "ep-2026-08-28-01", "date": "2026-08-28", "source_ref": "live:claude-ai",
             "trigger": "她十点没回消息", "my_thought": "她在跟别人玩", "certainty": 60, "urge": 6},
            {"op": "fact", "id": "ep-2026-08-28-01", "outcome": "not_happened", "outcome_fact": "十一点她发了在家的照片"},
            {"op": "drill", "date": "2026-10-26", "scene": "sc-2026-08-28-01", "view": "V01", "suds_before": 50,
             "suds_after": 30, "within_3s": True, "verbatim": True, "held_30s": True},
            {"op": "ladder", "id": "L01", "suds": 25, "date": "2026-10-26"},
            {"op": "view", "id": "V09"},
        ]
        inbox.write(self.life.paths, ops, self.life_day())
        results = service.ingest(self.life.paths, self.life_day())
        outcomes = [outcome for _, _, outcome in results]
        self.assertEqual(outcomes[0], "added")
        self.assertTrue(outcomes[1].startswith("updated"))
        self.assertEqual(outcomes[2], "added")
        self.assertTrue(outcomes[3].startswith("completed"))
        self.assertTrue(outcomes[4].startswith("failed"))
        rows = self.life.episodes()
        added = [row for row in rows if row["trigger"] == "她十点没回消息"][0]
        self.assertEqual((added["id"], added["outcome"], added["origin"]), ("ep-2026-08-28-02", "not_happened", "inbox"))
        self.assertEqual([op["id"] for op in inbox.read(self.life.paths)], ["V09"])
        again = service.ingest(self.life.paths, self.life_day())
        self.assertEqual(len(again), 1)
        self.assertEqual(len(self.life.episodes()), 2)

    def test_duplicate_episode_is_skipped(self):
        inbox.write(self.life.paths, [{"op": "episode", **episode()}], self.life_day())
        self.assertEqual(service.ingest(self.life.paths, self.life_day())[0][2], "duplicate")

    def life_day(self):
        return datetime(2026, 10, 26, tzinfo=TZ).date()


class ExtractTest(unittest.TestCase):
    def setUp(self):
        self.life = LifeOS()
        raw_conversation(self.life.repo, "conv-1", [
            ("m1", "user", "她说想自己待会，我又开始慌了，我觉得她是不是不要我了，胸口很闷"),
            ("m2", "assistant", "你觉得她是不是不要你了"),
            ("m3", "user", "分手以后我还是想找她"),
        ])

    def tearDown(self):
        self.life.close()

    def test_verbatim_and_role_checks(self):
        ref = "raw/conversations/2026-10/claude-a-1.jsonl#"
        rows = [{"id": "a", "source_ref": ref + "m1", "my_thought": "我觉得她是不是不要我了…胸口很闷", "body": "胸口很闷"},
                {"id": "b", "source_ref": ref + "m1", "my_thought": "她肯定变心了", "body": ""},
                {"id": "c", "source_ref": ref + "m2", "my_thought": "你觉得她是不是不要你了", "body": ""},
                {"id": "d", "source_ref": ref + "missing", "my_thought": "x", "body": ""}]
        problems = dict(extract.verify(self.life.repo, rows))
        self.assertNotIn("a", problems)
        self.assertEqual(problems["b"], "my_thought_not_verbatim")
        self.assertEqual(problems["c"], "source_is_not_my_message")
        self.assertEqual(problems["d"], "source_ref_not_found")

    def test_candidates_and_shards(self):
        out = self.life.repo / "shards"
        manifest, summary = extract.write_shards(self.life.repo, out, min_hits=1)
        self.assertEqual(summary[0]["hit_messages"], 2)
        text = (out / manifest[0]["shard"]).read_text(encoding="utf-8")
        self.assertIn("ref=raw/conversations/2026-10/claude-a-1.jsonl#m1 HIT:", text)
        self.assertIn("[assistant", text)

    def test_merge_numbers_verifies_and_is_idempotent(self):
        ref = "raw/conversations/2026-10/claude-a-1.jsonl#"
        good = {"date": "2026-10-24", "source_ref": ref + "m1", "trigger": "她说想自己待会",
                "my_thought": "我觉得她是不是不要我了", "body": "胸口很闷"}
        bad = dict(good, my_thought="她肯定变心了")
        added, rejected, _ = extract.merge(self.life.repo, [], [good, bad, dict(good)])
        self.assertEqual([row["id"] for row in added], ["ep-2026-10-24-01"])
        self.assertEqual((added[0]["origin"], added[0]["review"]), ("export", "pending"))
        self.assertEqual(rejected[0][1], "my_thought_not_verbatim")
        pending = dict(good, source_ref=ref + "m3", my_thought="", body="", outcome_fact="她第二天回来了")
        moved, _, _ = extract.merge(self.life.repo, added, [pending])
        self.assertEqual((moved[0]["outcome_fact"], moved[0]["notes"]), ("", "后续：她第二天回来了"))
        again, _, _ = extract.merge(self.life.repo, added, [good])
        self.assertEqual(again, [])
        twin = dict(good, my_thought="胸口很闷", trigger="她说想自己待会儿")
        _, _, duplicates = extract.merge(self.life.repo, added, [twin])
        self.assertEqual(duplicates, [("ep-2026-10-24-02", "ep-2026-10-24-01")])

    def test_scenes_from_candidates(self):
        row = episode("ep-2026-10-24-01", source_ref="raw/x.jsonl#m1", suds_peak=None)
        candidate = {"source_ref": "raw/x.jsonl#m1", "date": "2026-10-24", "cue": "",
                     "text": "我坐在床边，她说想自己待一会，我胸口一紧。", "script": "", "conditions": []}
        built, rejected = extract.scenes_from([row], [candidate, dict(candidate, text="他" * 200)])
        self.assertEqual((built[0].id, built[0].cue, built[0].suds_expected), ("sc-2026-10-24-01", "她说想自己待一会", 60))
        self.assertEqual(rejected[0][1], "duplicate_scene_for_episode")

    def test_ellipsis_keeps_order(self):
        self.assertTrue(extract.verbatim("我又开始慌了…胸口很闷", "她说想自己待会，我又开始慌了，胸口很闷"))
        self.assertFalse(extract.verbatim("胸口很闷…我又开始慌了", "我又开始慌了，胸口很闷"))


class RepoResolutionTest(unittest.TestCase):
    def test_env_and_skill_location(self):
        life = LifeOS()
        try:
            self.assertEqual(resolve_repo(env={"LIFE_OS_REPO": str(life.repo)}).repo, life.repo.resolve())
            home = life.repo / "home"
            location = home / ".claude/skills/life-os/references/location.json"
            location.parent.mkdir(parents=True)
            location.write_text(json.dumps({"knowledge_root": str(life.repo)}), encoding="utf-8")
            self.assertEqual(resolve_repo(env={}, home=home).repo, life.repo.resolve())
            with self.assertRaises(AnchorError):
                resolve_repo(env={}, home=life.repo / "nowhere")
            with self.assertRaises(AnchorError):
                resolve_repo(str(home))
        finally:
            life.close()


class WeeklyTest(unittest.TestCase):
    def test_calibration_buckets_and_brier(self):
        rows = [episode("ep-2026-10-26-01", certainty=90, outcome="not_happened"),
                episode("ep-2026-10-26-02", certainty=90, outcome="happened", outcome_fact="她真的走了"),
                episode("ep-2026-10-26-03", certainty=30, outcome="unverifiable", outcome_fact="")]
        result = weekly.calibration(rows)
        self.assertEqual(result["n"], 2)
        self.assertEqual(result["buckets"][0]["happened"], 0.5)
        self.assertAlmostEqual(result["brier"], (0.81 + 0.01) / 2)

    def test_week_bounds(self):
        self.assertEqual(weekly.week_bounds("2026-44")[0].isoformat(), "2026-10-26")


class ScriptEntryTest(unittest.TestCase):
    def test_runs_as_a_script(self):
        life = LifeOS()
        try:
            env = dict(os.environ, LIFE_OS_REPO=str(life.repo))
            result = subprocess.run(["python3", str(ROOT / "scripts/anchor.py"), "--today", "2026-10-26", "validate"],
                                    capture_output=True, text=True, env=env, cwd=Path("/"))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("0 error(s)", result.stdout)
        finally:
            life.close()


if __name__ == "__main__":
    unittest.main()
