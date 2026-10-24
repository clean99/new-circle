from datetime import datetime, timedelta
import unittest

from helpers import episode

from anchor_core import episodes
from anchor_core.store import TZ, AnchorError


class ValidateTest(unittest.TestCase):
    def test_complete_episode_is_valid(self):
        self.assertEqual(episodes.validate(episode()), ([], []))

    def test_pending_episode_allows_nulls(self):
        row = episode(action=None, outcome=None, outcome_fact="", miss=None, urge=None, certainty=None)
        self.assertEqual(episodes.validate(row)[0], [])

    def test_rejects_out_of_range_and_unknown_values(self):
        row = episode(urge=11, certainty=-1, action="begged", outcome="maybe", extra=1)
        errors, _ = episodes.validate(row)
        for code in ("urge_out_of_range", "certainty_out_of_range", "invalid_action", "invalid_outcome"):
            self.assertIn(code, errors)
        self.assertTrue(any(error.startswith("unknown_fields") for error in errors))

    def test_empty_thought_is_a_warning(self):
        self.assertEqual(episodes.validate(episode(my_thought="")), ([], ["my_thought_empty"]))

    def test_id_must_match_date(self):
        self.assertIn("id_date_mismatch", episodes.validate(episode(date="2026-08-29"))[0])

    def test_fact_required_for_verifiable_outcome(self):
        self.assertIn("outcome_fact_required", episodes.validate(episode(outcome_fact=""))[0])
        self.assertEqual(episodes.validate(episode(outcome="unverifiable", outcome_fact=""))[0], [])

    def test_miss_needs_an_action(self):
        self.assertIn("miss_requires_action", episodes.validate(episode(miss=True, action=None))[0])

    def test_warns_about_motive_in_trigger_and_explanation_as_fact(self):
        _, warnings = episodes.validate(episode(trigger="她故意不回消息", outcome_fact="她说只是朋友"))
        self.assertIn("trigger_mentions_motive", warnings)
        self.assertIn("outcome_fact_looks_like_explanation", warnings)


class FactTest(unittest.TestCase):
    def test_explanation_becomes_unverifiable(self):
        row = episode(outcome=None, outcome_fact="")
        updated, warnings = episodes.apply_fact(row, "not_happened", "她说不是跟男生出去")
        self.assertEqual(updated["outcome"], "unverifiable")
        self.assertEqual(warnings, ["explanation_recorded_as_unverifiable"])

    def test_observed_flag_keeps_outcome(self):
        row = episode(outcome=None, outcome_fact="")
        updated, warnings = episodes.apply_fact(row, "happened", "她在电话里说了分手", observed=True)
        self.assertEqual((updated["outcome"], warnings), ("happened", []))

    def test_observable_fact_kept(self):
        row = episode(outcome=None, outcome_fact="")
        updated, _ = episodes.apply_fact(row, "not_happened", "第二天早上 8 点她发了早安", recovery_minutes=30)
        self.assertEqual((updated["outcome"], updated["recovery_minutes"]), ("not_happened", 30))

    def test_thought_coming_true_is_still_a_valid_record(self):
        row = episode(outcome=None, outcome_fact="")
        updated, _ = episodes.apply_fact(row, "happened", "周六她没有回来吃饭")
        self.assertEqual(updated["outcome"], "happened")

    def test_requires_fact_text(self):
        with self.assertRaises(AnchorError):
            episodes.apply_fact(episode(), "happened", " ")


class IdsAndFollowUpTest(unittest.TestCase):
    def test_next_id_fills_gaps(self):
        day = datetime(2026, 10, 26).date()
        taken = {"ep-2026-10-26-01", "ep-2026-10-26-03"}
        self.assertEqual(episodes.next_id(day, taken), "ep-2026-10-26-02")

    def test_due_window(self):
        recorded = datetime(2026, 10, 26, 22, 0, tzinfo=TZ)
        row = episode("ep-2026-10-26-01", outcome=None, outcome_fact="", recorded_at=recorded.isoformat())
        self.assertEqual(episodes.due_follow_ups([row], recorded + timedelta(hours=23)), [])
        self.assertEqual(episodes.due_follow_ups([row], recorded + timedelta(hours=30))[0][1], "due")
        self.assertEqual(episodes.due_follow_ups([row], recorded + timedelta(hours=80))[0][1], "overdue")
        self.assertEqual(episodes.due_follow_ups([episode()], recorded + timedelta(hours=80)), [])
        history = episode("ep-2026-08-01-01", outcome=None, outcome_fact="", origin="export")
        self.assertEqual(episodes.due_follow_ups([history], recorded), [])


if __name__ == "__main__":
    unittest.main()
