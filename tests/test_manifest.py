import json
import tempfile
import unittest
from pathlib import Path

from bizfactcheck.core import verify_manifest


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.write("source.md", "The project budget is CNY 1.2 million.")
        self.draft = self.write("draft.md", "The proposed budget is 120万元.")

    def write(self, name, text):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def check(self):
        return {"field": "Project budget", "kind": "money",
                "source": {"path": "source.md", "quote": "The project budget is CNY 1.2 million.", "value": "CNY 1.2 million"},
                "draft": {"path": "draft.md", "quote": "The proposed budget is 120万元.", "value": "120万元"}}

    def run_manifest(self, checks):
        path = self.write("checks.json", json.dumps({"checks": checks}, ensure_ascii=False))
        return verify_manifest(path)

    def pair_report(self, source_text, source_quote, source_value,
                    draft_text, draft_quote, draft_value, kind):
        self.source.write_text(source_text, encoding="utf-8")
        self.draft.write_text(draft_text, encoding="utf-8")
        check = self.check()
        check["kind"] = kind
        check["source"].update(quote=source_quote, value=source_value)
        check["draft"].update(quote=draft_quote, value=draft_value)
        return self.run_manifest([check])

    def test_anchored_values_compare_with_relative_paths(self):
        report = self.run_manifest([self.check()])
        self.assertEqual(report["mode"], "verify")
        self.assertEqual(report["coverage"]["compared"], 1)
        self.assertEqual(report["findings"][0]["status"], "match")
        self.assertEqual(report["findings"][0]["source"]["location"], "line 1")
        self.assertEqual(set(report["input_paths"]),
                         {str(self.source.resolve()), str(self.draft.resolve()), str((self.root / "checks.json").resolve())})

    def test_whitespace_normalized_quote_can_span_lines(self):
        self.source.write_text("The project budget\nis  CNY 1.2 million.\n", encoding="utf-8")
        report = self.run_manifest([self.check()])
        self.assertEqual(report["findings"][0]["status"], "match")
        self.assertEqual(report["findings"][0]["source"]["location"], "line 1 - line 2")

    def test_valid_anchors_can_show_a_conflict(self):
        self.draft.write_text("The proposed budget is 12000万元.", encoding="utf-8")
        check = self.check()
        check["draft"].update(quote="The proposed budget is 12000万元.", value="12000万元")
        self.assertEqual(self.run_manifest([check])["findings"][0]["status"], "conflict")

    def test_missing_evidence_path_quote_and_value_are_reviews(self):
        for side in ["source", "draft"]:
            for key, reason in [(None, "missing_evidence"), ("path", "missing_path"),
                                ("quote", "missing_quote"), ("value", "missing_value")]:
                with self.subTest(side=side, key=key):
                    check = self.check()
                    if key is None:
                        del check[side]
                    else:
                        del check[side][key]
                    report = self.run_manifest([check])
                    self.assertEqual(report["findings"][0]["reason"], reason)
                    self.assertEqual(report["findings"][0]["status"], "review")
                    self.assertEqual(report["coverage"]["compared"], 0)

    def test_quote_not_found_and_duplicate_quote_require_review(self):
        check = self.check()
        check["source"]["quote"] = "The source says CNY 1.2 million."
        self.assertEqual(self.run_manifest([check])["findings"][0]["reason"], "quote_not_found")
        self.source.write_text("The project budget is CNY 1.2 million.\nThe project budget is CNY 1.2 million.", encoding="utf-8")
        report = self.run_manifest([self.check()])
        self.assertEqual(report["findings"][0]["reason"], "ambiguous_quote")
        self.assertEqual(report["coverage"]["compared"], 0)

    def test_value_must_occur_in_its_quote_without_numeric_substring_trick(self):
        for value in ["CNY 120 million", "2 million"]:
            with self.subTest(value=value):
                check = self.check()
                check["source"]["value"] = value
                self.assertEqual(self.run_manifest([check])["findings"][0]["reason"], "value_not_in_quote")

    def test_value_repeated_within_quote_is_ambiguous(self):
        self.source.write_text("The budget is CNY 1.2 million and the fee is CNY 1.2 million.", encoding="utf-8")
        check = self.check()
        check["source"]["quote"] = self.source.read_text(encoding="utf-8")
        self.assertEqual(self.run_manifest([check])["findings"][0]["reason"], "ambiguous_value")

    def test_omitting_a_qualifier_from_extracted_value_needs_review(self):
        self.source.write_text("The project budget is at most CNY 1.2 million.", encoding="utf-8")
        check = self.check()
        check["source"]["quote"] = self.source.read_text(encoding="utf-8")
        self.assertEqual(self.run_manifest([check])["findings"][0]["reason"], "qualified_value")

    def test_value_cannot_omit_a_following_scale_or_unit(self):
        for quote, value, kind in [("Budget: USD 1 million.", "USD 1", "money"),
                                   ("Reporting period: 2025年上半年。", "2025", "period"),
                                   ("Rate: 5 percentage points.", "5", "percentage")]:
            with self.subTest(quote=quote):
                self.source.write_text(quote, encoding="utf-8")
                check = self.check()
                check["kind"] = kind
                check["source"].update(quote=quote, value=value)
                self.assertEqual(self.run_manifest([check])["findings"][0]["reason"], "value_not_in_quote")

    def test_number_at_sentence_end_is_a_valid_literal_anchor(self):
        self.source.write_text("Reporting period: 2025.", encoding="utf-8")
        self.draft.write_text("The reporting year is 2025.", encoding="utf-8")
        check = self.check()
        check["kind"] = "period"
        check["source"].update(quote="Reporting period: 2025.", value="2025")
        check["draft"].update(quote="The reporting year is 2025.", value="2025")
        self.assertEqual(self.run_manifest([check])["findings"][0]["status"], "match")

    def test_negated_stage_cannot_be_presented_as_the_positive_stage(self):
        self.source.write_text("The system is not deployed.", encoding="utf-8")
        self.draft.write_text("The system is deployed.", encoding="utf-8")
        check = self.check()
        check["kind"] = "status"
        check["source"].update(quote="The system is not deployed.", value="deployed")
        check["draft"].update(quote="The system is deployed.", value="deployed")
        self.assertEqual(self.run_manifest([check])["findings"][0]["reason"], "qualified_value")

    def test_quote_boundaries_are_checked_against_original_document(self):
        cases = [
            ("The approved budget is USD 10 million.", "USD 10", "money"),
            ("甲项目预算为120万元。", "20万元", "money"),
            ("The reporting period is H1 2026.", "2026", "period"),
            ("报告期为2026年上半年。", "2026年", "period"),
            ("调整额为－120万元。", "120万元", "money"),
            ("The rebate is 2.5%.", "5%", "percentage"),
        ]
        for source_text, quote, kind in cases:
            with self.subTest(source=source_text, quote=quote):
                report = self.pair_report(source_text, quote, quote,
                                          "Claim: " + quote, "Claim: " + quote, quote, kind)
                self.assertEqual(report["findings"][0]["reason"], "incomplete_quote")
                self.assertEqual(report["findings"][0]["status"], "review")
                self.assertEqual(report["coverage"]["compared"], 0)

    def test_complete_quote_does_not_allow_incomplete_numeric_values(self):
        cases = [
            ("The reporting period is H1 2026.", "2026", "period"),
            ("报告期为2026年上半年。", "2026年", "period"),
            ("The adjustment is -USD 15.", "USD 15", "money"),
            ("调整额为－120万元。", "120万元", "money"),
            ("调整额为−120万元。", "120万元", "money"),
            ("收入为120万美元。", "120万", "text"),
            ("The fee is USD 800 per month.", "USD 800", "money"),
            ("The fee is USD 800/month.", "USD 800", "money"),
        ]
        for source_text, value, kind in cases:
            with self.subTest(source=source_text, value=value):
                report = self.pair_report(source_text, source_text, value,
                                          "Claim: " + value, "Claim: " + value, value, kind)
                self.assertEqual(report["findings"][0]["reason"], "value_not_in_quote")
                self.assertEqual(report["coverage"]["compared"], 0)

    def test_cropped_quote_does_not_remove_original_qualifiers(self):
        for source_text, value, kind in [
                ("The budget is at most USD 10 million.", "USD 10 million", "money"),
                ("项目预算约为120万元。", "120万元", "money"),
                ("The service is not deployed.", "deployed", "status"),
                ("现场系统尚未正式上线。", "正式上线", "status"),
                ("The service does not include hosting.", "hosting", "text")]:
            with self.subTest(source=source_text):
                report = self.pair_report(source_text, value, value,
                                          "Claim: " + value, "Claim: " + value, value, kind)
                self.assertEqual(report["findings"][0]["status"], "review")
                self.assertEqual(report["findings"][0]["reason"], "qualified_value")

    def test_standard_negative_contractions_require_stage_review(self):
        for contraction in ["isn't", "isn’t", "wasn't", "aren't", "hasn't", "haven't", "can't", "cannot"]:
            with self.subTest(contraction=contraction):
                source_text = "The system " + contraction + " deployed."
                report = self.pair_report(source_text, source_text, "deployed",
                                          "The system is deployed.", "The system is deployed.", "deployed", "status")
                self.assertEqual(report["findings"][0]["reason"], "qualified_value")

    def test_complete_numeric_fragments_and_normal_sentences_remain_usable(self):
        cases = [
            ("The budget is USD 10 million.", "USD 10 million", "USD 10 million", "USD 10,000,000", "money"),
            ("甲项目预算为120万元。", "120万元", "120万元", "CNY 1.2 million", "money"),
            ("The period is H1 2026.", "H1 2026", "H1 2026", "2026年上半年", "period"),
            ("The period is Q2 2026.", "Q2 2026", "Q2 2026", "2026年第二季度", "period"),
            ("调整额为－120万元。", "－120万元", "－120万元", "CNY -1.2 million", "money"),
            ("The system is deployed.", "deployed", "deployed", "已部署", "status"),
            ("The year is 2026.", "The year is 2026.", "2026", "2026年度", "period"),
            ("The service does not include hosting.", "The service does not include hosting.",
             "The service does not include hosting.", "The service does not include hosting.", "text"),
        ]
        for source_text, quote, value, draft_value, kind in cases:
            with self.subTest(source=source_text):
                report = self.pair_report(source_text, quote, value,
                                          draft_value, draft_value, draft_value, kind)
                self.assertEqual(report["findings"][0]["status"], "match")
                self.assertEqual(report["coverage"]["compared"], 1)

    def test_partial_words_are_not_valid_quotes(self):
        report = self.pair_report("The approved budget is USD 10 million.", "udget is USD 10 million", "USD 10 million",
                                  "USD 10 million", "USD 10 million", "USD 10 million", "money")
        self.assertEqual(report["findings"][0]["reason"], "incomplete_quote")

    def test_contract_word_is_not_an_approximate_amount(self):
        report = self.pair_report("合同约定预算为120万元。", "合同约定预算为120万元。", "120万元",
                                  "预算为120万元。", "预算为120万元。", "120万元", "money")
        self.assertEqual(report["findings"][0]["status"], "match")

    def test_mixed_valid_and_invalid_checks_keep_the_good_comparison(self):
        bad = self.check()
        bad["field"] = "Unanchored claim"
        bad["draft"]["quote"] = "This sentence is not in the file."
        report = self.run_manifest([self.check(), bad])
        self.assertEqual(report["coverage"]["compared"], 1)
        self.assertEqual([item["status"] for item in report["findings"]], ["match", "review"])

    def test_empty_invalid_json_and_invalid_structures_raise(self):
        for data in ["", "not JSON", "{}", '{"checks": []}', '{"checks": [1]}',
                     '{"checks": [{"field": ""}]}',
                     '{"checks": [], "checks": [{"field": "Budget"}]}']:
            with self.subTest(data=data):
                path = self.write("checks.json", data)
                with self.assertRaises(ValueError):
                    verify_manifest(path)
        check = self.check()
        check["kind"] = "unsupported"
        with self.assertRaises(ValueError):
            self.run_manifest([check])

    def test_unreadable_and_unsupported_references_raise(self):
        for name, exception in [("missing.md", OSError), ("input.pdf", ValueError),
                                (".env", ValueError)]:
            with self.subTest(name=name):
                check = self.check()
                check["source"]["path"] = name
                with self.assertRaises(exception):
                    self.run_manifest([check])


if __name__ == "__main__":
    unittest.main()
