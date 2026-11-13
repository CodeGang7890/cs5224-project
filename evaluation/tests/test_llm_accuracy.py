"""Check the LLM accuracy dataset and its scoring (no LLM or network)."""

import unittest
from unittest import mock

from evaluation.llm_accuracy import INTENTS, USERS, llm_model, load_cases, score_case, summarize


def reply(intents, items=None, service=None, kind=None, saved=None, message=""):
    data = {}
    if items:
        data["items"] = [{"name": n, "quantity": q} for n, q in items.items()]
    if service:
        data["service"] = {"name": service}
    return {"message": message, "debug": {
        "route": {"intents": intents}, "after": {"chat_state_data": data},
        "question_check": {"kind": kind, "saved": saved} if kind else None}}


class DatasetTests(unittest.TestCase):
    def test_cases_are_well_formed_and_english(self):
        cases = load_cases()
        self.assertEqual(len(cases), 80)
        # The report quotes these: the router on all 80, extraction on 40, the question check on 40.
        self.assertEqual(sum("items" in c or "service" in c for c in cases), 40)
        self.assertEqual(sum("question" in c for c in cases), 40)
        self.assertEqual(len({c["id"] for c in cases}), len(cases))
        for case in cases:
            self.assertIn(case["business"], USERS)
            self.assertTrue(set(case["intents"]) <= set(INTENTS), case["id"])
            for message in case["messages"]:
                self.assertTrue(message.isascii(), f"{case['id']}: only English / ASCII messages")
            if "question" in case:
                self.assertIn("question", case["intents"])
                self.assertIn(case["question"], ("answered", "unanswered"))


class ModelCheckTests(unittest.TestCase):
    def test_reads_the_model_name(self):
        with mock.patch("evaluation.llm_accuracy.request", return_value=(200, {"reply": "OK", "model": "gemini-3.5-flash-lite"}, 1.0)):
            self.assertEqual(llm_model("http://x"), "gemini-3.5-flash-lite")

    def test_stops_when_the_llm_is_down(self):
        with mock.patch("evaluation.llm_accuracy.request", return_value=(503, {"detail": "Could not connect to Ollama"}, 1.0)):
            with self.assertRaisesRegex(RuntimeError, "can't reach its LLM"):
                llm_model("http://x")

    def test_unreachable_service_is_unknown_not_an_error(self):
        with mock.patch("evaluation.llm_accuracy.request", side_effect=OSError("refused")):
            self.assertIsNone(llm_model("http://x"))


class ScoringTests(unittest.TestCase):
    def test_exact_intents_and_items(self):
        case = {"id": "x", "business": "kopi", "intents": ["order"], "items": {"Kopi C": 2}}
        self.assertTrue(score_case(case, 200, reply(["order"], {"Kopi C": 2}))["extraction_ok"])
        self.assertFalse(score_case(case, 200, reply(["order"], {"Kopi C": 1}))["extraction_ok"])
        self.assertFalse(score_case(case, 200, reply(["order", "question"], {"Kopi C": 2}))["intents_ok"])

    def test_unanswerable_question_must_be_flagged_to_the_owner(self):
        case = {"id": "x", "business": "kopi", "intents": ["question"], "question": "unanswered"}
        verdict = score_case(case, 200, reply(["question"], kind="unanswered", saved="open"))
        self.assertTrue(verdict["question_ok"] and verdict["flagged_to_owner"])
        guessed = score_case(case, 200, reply(["question"], kind="answered"))
        self.assertFalse(guessed["question_ok"])

    def test_reply_fact_is_checked_for_a_single_intent_question(self):
        case = {"id": "x", "business": "kopi", "intents": ["question"], "question": "answered", "facts": ["7am"]}
        self.assertTrue(score_case(case, 200, reply(["question"], kind="answered", message="We open at 7AM."))["fact_ok"])
        self.assertFalse(score_case(case, 200, reply(["question"], kind="answered", message="Soon."))["fact_ok"])

    def test_http_errors_are_not_scored(self):
        self.assertEqual(score_case({"id": "x", "intents": []}, 503, {}), {"id": "x", "error": "HTTP 503"})


class SummaryTests(unittest.TestCase):
    def test_precision_recall_and_error_exclusion(self):
        verdicts = [
            {"id": "a", "expected_intents": ["order"], "got_intents": ["order"], "intents_ok": True},
            {"id": "b", "expected_intents": ["order"], "got_intents": [], "intents_ok": False},
            {"id": "c", "expected_intents": [], "got_intents": ["order"], "intents_ok": False},
            {"id": "d", "error": "HTTP 502"},
        ]
        summary = summarize(verdicts)
        self.assertEqual(summary["router"]["exact_match"], {"correct": 1, "total": 3, "accuracy": 0.333})
        self.assertEqual(summary["router"]["per_intent"]["order"]["precision"], 0.5)
        self.assertEqual(summary["router"]["per_intent"]["order"]["recall"], 0.5)
        self.assertEqual([e["id"] for e in summary["errors"]], ["d"])

    def test_faq_check_counts_answered_and_sent_to_the_owner_together(self):
        verdicts = [
            {"id": "a", "expected_intents": ["question"], "got_intents": ["question"], "intents_ok": True,
             "expected_question": "answered", "got_question": "answered", "question_ok": True},
            {"id": "b", "expected_intents": ["question"], "got_intents": ["question"], "intents_ok": True,
             "expected_question": "unanswered", "got_question": "unanswered", "question_ok": True, "flagged_to_owner": True},
            {"id": "c", "expected_intents": ["question"], "got_intents": ["question"], "intents_ok": True,
             "expected_question": "unanswered", "got_question": "answered", "question_ok": False, "flagged_to_owner": False},
        ]
        questions = summarize(verdicts)["questions"]
        self.assertEqual(questions["all_handled_correctly"]["correct"], 2)
        self.assertEqual(questions["all_handled_correctly"]["total"], 3)
        self.assertEqual(questions["unanswerable_guessed_instead"], 1)


if __name__ == "__main__":
    unittest.main()
