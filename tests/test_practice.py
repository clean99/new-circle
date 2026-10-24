from dataclasses import replace
from datetime import date, timedelta
import unittest

from helpers import ACTIONS, DAY, LADDER, SCENE, VIEWS, episode

from anchor_core import actions, drills, ladder, scenes, views
from anchor_core.store import AnchorError


class ViewsTest(unittest.TestCase):
    def test_parse_and_due(self):
        parsed = views.parse(VIEWS)
        self.assertEqual([view.id for view in parsed], ["V01", "V02"])
        self.assertEqual(views.due(parsed, DAY).id, "V01")
        self.assertEqual(views.validate(parsed), [])

    def test_schedule_follows_1_3_7_14_30(self):
        view = views.parse(VIEWS)[0]
        gaps = []
        day = DAY
        for _ in range(6):
            view = views.reviewed(view, day)
            gaps.append((view.due - day).days)
            day = view.due
        self.assertEqual(gaps, [1, 3, 7, 14, 30, 30])

    def test_again_restarts_tomorrow(self):
        view = views.reviewed(views.parse(VIEWS)[1], DAY, remembered=False)
        self.assertEqual((view.stage, view.due), (0, DAY + timedelta(days=1)))

    def test_update_rewrites_only_review_line(self):
        parsed = views.parse(VIEWS)
        text = views.update(VIEWS, views.reviewed(parsed[0], DAY))
        self.assertIn("下次 2026-10-27｜上次 2026-10-26", text)
        self.assertEqual(text.count("\n"), VIEWS.count("\n"))
        self.assertEqual(views.parse(text)[1], parsed[1])

    def test_stated_view_needs_quote_and_raw_source(self):
        bad = VIEWS.replace("「我只依靠事实去做决定」— raw/conversations/2026-10/claude-a-1.jsonl#m1", "我说过")
        self.assertEqual(len(views.validate(views.parse(bad))), 2)

    def test_broken_block_is_an_error(self):
        with self.assertRaises(AnchorError):
            views.parse("- **V09** 没有出处")


class LadderTest(unittest.TestCase):
    def test_current_and_clearing(self):
        text = LADDER
        self.assertEqual(ladder.current(ladder.parse(text)).id, "L01")
        text = ladder.complete(text, "L01", DAY, 60)
        self.assertEqual(ladder.current(ladder.parse(text)).id, "L01")
        text = ladder.complete(text, "L01", DAY + timedelta(days=2), 35, "说完有点脸热")
        rungs = ladder.parse(text)
        self.assertTrue(rungs[0].cleared)
        self.assertIn("- [x] **L01**", text)
        self.assertEqual(ladder.current(rungs).id, "L02")
        self.assertEqual(rungs[0].completions[1][2], "说完有点脸热")

    def test_high_suds_does_not_clear(self):
        text = ladder.complete(ladder.complete(LADDER, "L01", DAY, 70), "L01", DAY, 55)
        self.assertFalse(ladder.parse(text)[0].cleared)

    def test_rejects_bad_input(self):
        with self.assertRaises(AnchorError):
            ladder.complete(LADDER, "L09", DAY, 10)
        with self.assertRaises(AnchorError):
            ladder.complete(LADDER, "L01", DAY, 101)


class ScenesTest(unittest.TestCase):
    def test_parse_and_validate(self):
        scene = scenes.parse(SCENE)
        self.assertEqual((scene.episode, scene.script, scene.conditions),
                         ("ep-2026-08-28-01", "好，你先休息。", ("电话", "半夜")))
        self.assertEqual(scenes.validate(scene, {"ep-2026-08-28-01"}), ([], []))

    def test_length_person_and_tense_rules(self):
        scene = scenes.parse(SCENE)
        long_scene = replace(scene, text="我" + "很" * 150)
        self.assertTrue(any(error.startswith("scene_text_too_long") for error in scenes.validate(long_scene)[0]))
        third = replace(scene, text="他当时坐着，心跳很快。")
        errors, warnings = scenes.validate(third)
        self.assertIn("scene_must_be_first_person", errors)
        self.assertIn("scene_contains_past_tense_marker", warnings)

    def test_render_round_trip(self):
        scene = scenes.parse(SCENE)
        again = scenes.parse(scenes.render(scene, DAY, "> 原话"))
        self.assertEqual((again.id, again.text, again.cue), (scene.id, scene.text, scene.cue))


class DrillsTest(unittest.TestCase):
    def setUp(self):
        base = scenes.parse(SCENE)
        self.a = base
        self.b = replace(base, id="sc-2026-09-01-01", conditions=("文字",))

    def test_unpractised_scene_first_then_spacing(self):
        state = {self.a.id: (1, DAY, 0)}
        self.assertEqual(drills.choose([self.a, self.b], state, {}, DAY).id, self.b.id)

    def test_miss_conditions_weight(self):
        state = {self.a.id: (1, DAY - timedelta(days=1), 0), self.b.id: (1, DAY - timedelta(days=1), 0)}
        misses = drills.recent_miss_conditions([episode(miss=True, miss_conditions=["文字"])],
                                               date(2026, 9, 5))
        self.assertEqual(drills.choose([self.a, self.b], state, misses, date(2026, 9, 5)).id, self.b.id)

    def test_low_suds_scene_pushed_back(self):
        state = {self.a.id: (2, DAY - timedelta(days=3), 2), self.b.id: (2, DAY - timedelta(days=3), 0)}
        self.assertEqual(drills.choose([self.a, self.b], state, {}, DAY).id, self.b.id)

    def test_script_has_the_ten_minute_flow(self):
        view = views.parse(VIEWS)[0]
        text = drills.script(self.a, view, DAY, hot=True)
        for part in ("60 秒", "接地", "读剧本", "3 秒内出声", "30 秒", "见地 V01", "SUDS", "drill log"):
            self.assertIn(part, text)
        self.assertIn("（电话）对方：「我想自己待一会。」→ 我：「好，你先休息。」", text)

    def test_plan_rotates_views_and_scenes(self):
        plan = drills.plan([self.a, self.b], views.parse(VIEWS), [], [], DAY, 4)
        self.assertEqual(len(plan), 4)
        self.assertEqual({scene.id for _, scene, _ in plan[:2]}, {self.a.id, self.b.id})
        self.assertEqual(plan[0][2].id, "V01")
        self.assertNotEqual(plan[1][2].id, "V01")

    def test_plan_never_repeats_a_scene_on_consecutive_days(self):
        third = replace(self.a, id="sc-2026-09-02-01", conditions=("当面",))
        misses = [episode(miss=True, miss_conditions=["电话"], date="2026-10-20", id="ep-2026-10-20-01")]
        plan = drills.plan([self.a, self.b, third], views.parse(VIEWS), [], misses, DAY, 7)
        ids = [scene.id for _, scene, _ in plan]
        self.assertTrue(all(left != right for left, right in zip(ids, ids[1:])))
        self.assertEqual(ids[0], self.a.id)
        self.assertEqual(len(set(ids)), 3)

    def test_validate_row(self):
        row = {"id": "dr-2026-10-26-01", "date": "2026-10-26", "scene": self.a.id, "view": "V01", "hot": False,
               "suds_before": 60, "suds_after": 30, "within_3s": True, "verbatim": True, "held_30s": True,
               "notes": ""}
        self.assertEqual(drills.validate(row), [])
        self.assertIn("suds_after_out_of_range", drills.validate({**row, "suds_after": 300}))


class ActionsTest(unittest.TestCase):
    def test_pick_is_deterministic(self):
        groups = actions.parse(ACTIONS)
        self.assertEqual(set(groups), {"事业", "健康", "社交"})
        self.assertEqual(actions.pick(groups, "ep-1"), actions.pick(groups, "ep-1"))
        picks = {actions.pick(groups, f"ep-{n}") for n in range(30)}
        self.assertEqual(len(picks), 3)


if __name__ == "__main__":
    unittest.main()
