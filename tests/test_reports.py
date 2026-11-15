"""Report behavior against complete, hand-checked core report fixtures."""

import copy
from html.parser import HTMLParser
import json
import unittest

from bizfactcheck.reports import render_report


def sample_report():
    return {
        "version": "0.1.0",
        "mode": "check",
        "findings": [
            {
                "field": "Project budget",
                "status": "conflict",
                "reason": "different_value",
                "source": {
                    "path": "reference.md",
                    "location": "line 2",
                    "quote": "Project budget: CNY 1.2 million",
                    "value": "CNY 1.2 million",
                },
                "draft": {
                    "path": "proposal.md",
                    "location": "line 4",
                    "quote": "Project budget: CNY 120 million",
                    "value": "CNY 120 million",
                },
            },
            {
                "field": "Project stage",
                "status": "review",
                "reason": "stage_changed",
                "source": {
                    "path": "reference.md",
                    "location": "line 3",
                    "quote": "Project stage: pilot",
                    "value": "pilot",
                },
                "draft": {
                    "path": "proposal.md",
                    "location": "line 5",
                    "quote": "Project stage: deployed",
                    "value": "deployed",
                },
            },
            {
                "field": "Service term",
                "status": "match",
                "reason": "equivalent_value",
                "source": {
                    "path": "reference.docx",
                    "location": "table 1, row 2",
                    "quote": "Service term | 24 hours",
                    "value": "24 hours",
                },
                "draft": {
                    "path": "proposal.md",
                    "location": "line 6",
                    "quote": "Service term: 1 day",
                    "value": "1 day",
                },
            },
        ],
        "coverage": {
            "compared": 3,
            "source_fields": 4,
            "draft_fields": 4,
            "uncompared_source_fields": ["Revenue"],
            "unpaired_draft_fields": ["New service"],
            "unpaired_prose_blocks": 2,
        },
        "input_paths": ["reference.md", "reference.docx", "proposal.md"],
    }


class ParsedHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.attrs = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend(attrs)

    def handle_data(self, data):
        self.text.append(data)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.report = sample_report()

    def test_json_preserves_machine_keys_reason_codes_and_original_report(self):
        original = copy.deepcopy(self.report)
        english = json.loads(render_report(self.report, "en", "json"))
        chinese = json.loads(render_report(self.report, "zh", "json"))
        self.assertEqual(set(english), set(chinese))
        self.assertEqual(english["summary"], {"conflict": 1, "review": 1, "match": 1})
        self.assertEqual(chinese["summary"], english["summary"])
        self.assertEqual(chinese["coverage"], self.report["coverage"])
        self.assertEqual(chinese["input_paths"], self.report["input_paths"])
        self.assertEqual(chinese["findings"][0]["reason"], "different_value")
        self.assertEqual(chinese["findings"][0]["status"], "conflict")
        self.assertEqual(chinese["findings"][0]["source"], self.report["findings"][0]["source"])
        self.assertNotEqual(english["findings"][0]["explanation"], chinese["findings"][0]["explanation"])
        self.assertEqual(self.report, original)

    def test_every_format_reports_evidence_locations_values_and_coverage_limits(self):
        for format in ("text", "json", "md", "html"):
            with self.subTest(format=format):
                rendered = render_report(self.report, "en", format)
                if format == "html":
                    parsed = ParsedHTML()
                    parsed.feed(rendered)
                    rendered = " ".join(parsed.text)
                self.assertIn("reference.md", rendered)
                self.assertIn("line 2", rendered)
                self.assertIn("table 1, row 2", rendered)
                self.assertIn("CNY 120 million", rendered)
                self.assertIn("Revenue", rendered)
                self.assertIn("New service", rendered)
                self.assertIn("listed fields", rendered)
                self.assertIn("DOCX", rendered)
                self.assertIn("headers", rendered)
                self.assertIn("text boxes", rendered)

    def test_human_formats_distinguish_outcomes_in_both_languages(self):
        for format in ("text", "md", "html"):
            for lang, labels in (("en", ("Differences", "Needs review", "Consistent")), ("zh", ("差异", "待复核", "一致"))):
                with self.subTest(format=format, lang=lang):
                    rendered = render_report(self.report, lang, format)
                    for label in labels:
                        self.assertIn(label, rendered)
                    self.assertIn("3", rendered)
        chinese = render_report(self.report, "zh", "text")
        self.assertIn("仅核对列出的字段", chinese)
        self.assertIn("原文", chinese)
        self.assertIn("位置", chinese)

    def test_html_treats_every_evidence_and_coverage_value_as_untrusted_text(self):
        attack = '<img src="https://example.invalid/x" onerror="alert(1)"><script>boom()</script>&'
        finding = self.report["findings"][0]
        finding["field"] = attack
        finding["reason"] = attack
        for side in ("source", "draft"):
            for key in ("path", "location", "quote", "value"):
                finding[side][key] = attack
        self.report["coverage"]["uncompared_source_fields"] = [attack]
        self.report["coverage"]["unpaired_draft_fields"] = [attack]
        rendered = render_report(self.report, "en", "html")
        parsed = ParsedHTML()
        parsed.feed(rendered)
        self.assertIn("html", parsed.tags)
        self.assertNotIn("script", parsed.tags)
        self.assertNotIn("img", parsed.tags)
        self.assertNotIn("iframe", parsed.tags)
        self.assertNotIn("link", parsed.tags)
        self.assertFalse(any(name.startswith("on") or name in ("src", "href") for name, _ in parsed.attrs))
        self.assertIn(attack, "".join(parsed.text))
        self.assertIn("&lt;script&gt;", rendered)

    def test_markdown_escapes_html_and_does_not_create_evidence_links(self):
        self.report["findings"][0]["field"] = '<script>bad()</script>[run](javascript:boom)'
        self.report["findings"][0]["source"]["quote"] = "a | b\n# injected heading"
        rendered = render_report(self.report, "en", "md")
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("[run](javascript:boom)", rendered)
        self.assertNotIn("\n# injected heading", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_zero_coverage_report_never_describes_result_as_consistent(self):
        self.report["coverage"]["compared"] = 0
        self.report["findings"] = []
        for lang, message in (("en", "No comparable pairs"), ("zh", "没有可比较的字段对")):
            for format in ("text", "md", "html"):
                with self.subTest(lang=lang, format=format):
                    self.assertIn(message, render_report(self.report, lang, format))

    def test_manifest_review_can_show_missing_evidence_and_unknown_reason(self):
        self.report["mode"] = "verify"
        self.report["coverage"]["compared"] = 0
        self.report["findings"] = [{"field": "Budget", "status": "review", "reason": "future_reason", "source": None, "draft": None}]
        for format in ("text", "md", "html", "json"):
            with self.subTest(format=format):
                rendered = render_report(self.report, "en", format)
                self.assertIn("human review", rendered)
                self.assertIn("semantic", rendered)

    def test_reason_explanations_cover_manifest_and_value_review_failures(self):
        reasons = (
            "currency_mismatch", "unit_mismatch", "qualified_value", "unsupported_value",
            "type_mismatch", "stage_changed", "text_changed", "missing_value", "ambiguous_field",
            "missing_evidence", "missing_path", "missing_quote", "quote_not_found",
            "ambiguous_quote", "value_not_in_quote", "ambiguous_value", "incomplete_quote",
        )
        explanations = set()
        for reason in reasons:
            self.report["findings"][0].update(status="review", reason=reason)
            parsed = json.loads(render_report(self.report, "en", "json"))
            explanation = parsed["findings"][0]["explanation"]
            self.assertTrue(explanation)
            explanations.add(explanation)
        self.assertEqual(len(explanations), len(reasons))

    def test_incomplete_quote_explains_how_to_restore_evidence_in_both_languages(self):
        self.report["mode"] = "verify"
        self.report["findings"][0].update(status="review", reason="incomplete_quote")
        for lang, guidance in (("en", ("quote", "full sentence")), ("zh", ("引文", "完整原句"))):
            with self.subTest(lang=lang):
                parsed = json.loads(render_report(self.report, lang, "json"))
                finding = parsed["findings"][0]
                self.assertEqual(finding["status"], "review")
                self.assertEqual(finding["reason"], "incomplete_quote")
                for phrase in guidance:
                    self.assertIn(phrase, finding["explanation"])

    def test_invalid_render_options_are_rejected(self):
        with self.assertRaises(ValueError):
            render_report(self.report, "fr", "html")
        with self.assertRaises(ValueError):
            render_report(self.report, "en", "pdf")


if __name__ == "__main__":
    unittest.main()
