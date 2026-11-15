import tempfile
import unittest
import zipfile
from pathlib import Path

from bizfactcheck.core import check_documents


class CheckDocumentsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_bilingual_fields_pair_and_preserve_evidence(self):
        source = self.write("source.md", "项目预算：120万元\n营收：500万元\n报告期：2025年上半年\n项目阶段：试点\n服务期限：24个月\n服务范围：Consulting only\n")
        draft = self.write("draft.md", "Project budget: CNY 1.2 million\nRevenue: CNY 5 million\nReporting period: H1 2025\nProject stage: pilot\nService term: 2 years\nService scope: consulting only\n")
        report = check_documents(source, [draft])
        self.assertEqual(report["mode"], "check")
        self.assertEqual(report["coverage"]["compared"], 6)
        self.assertEqual(report["coverage"]["source_fields"], 6)
        self.assertEqual(report["coverage"]["draft_fields"], 6)
        self.assertEqual([item["status"] for item in report["findings"]], ["match"] * 6)
        item = report["findings"][0]
        self.assertEqual(item["source"], {"path": str(source.resolve()), "location": "line 1",
                                          "quote": "项目预算：120万元", "value": "120万元"})
        self.assertEqual(item["draft"]["value"], "CNY 1.2 million")
        self.assertEqual(set(report["input_paths"]), {str(source.resolve()), str(draft.resolve())})

    def test_differences_review_stages_and_conflict_for_numbers_and_periods(self):
        source = self.write("source.txt", "Budget: CNY 1 million\nReporting period: 2025 H1\nStage: pilot\nScope: support\n")
        draft = self.write("draft.txt", "Budget: CNY 2 million\nReporting period: 2025\nStage: deployed\nScope: support and hosting\n")
        self.assertEqual([item["status"] for item in check_documents(source, [draft])["findings"]],
                         ["conflict", "conflict", "review", "review"])

    def test_markdown_tables_skip_headers_and_alignment_rows(self):
        source = self.write("source.md", "| Field | Value |\n| :--- | ---: |\n| Project budget | CNY 1.2 million |\n| Service scope | A \\| B |\n")
        draft = self.write("draft.md", "| 字段 | 值 |\n| --- | --- |\n| 项目预算 | 120万元 |\n| 服务范围 | A \\| B |\n")
        report = check_documents(source, [draft])
        self.assertEqual(report["coverage"]["compared"], 2)
        self.assertEqual(report["coverage"]["source_fields"], 2)
        self.assertEqual([item["status"] for item in report["findings"]], ["match", "match"])

    def test_arbitrary_markdown_headers_do_not_create_false_coverage(self):
        source = self.write("source.md", "| Item | Approved fact |\n| --- | --- |\n| Owner | Example team |")
        draft = self.write("draft.md", "| Item | Approved fact |\n| --- | --- |\n| Audience | Example group |")
        with self.assertRaises(ValueError):
            check_documents(source, [draft])

    def test_docx_two_column_table_is_compared(self):
        source = self.root / "source.docx"
        with zipfile.ZipFile(source, "w") as package:
            package.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Project budget</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>CNY 1 million</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
        draft = self.write("draft.txt", "项目预算：100万元")
        report = check_documents(source, [draft])
        self.assertEqual(report["findings"][0]["status"], "match")
        self.assertEqual(report["findings"][0]["source"]["location"], "table 1 row 1")

    def test_docx_empty_table_value_is_visible_as_missing(self):
        source = self.root / "source.docx"
        with zipfile.ZipFile(source, "w") as package:
            package.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Budget</w:t></w:r></w:p></w:tc><w:tc><w:p/></w:tc></w:tr></w:tbl></w:body></w:document>')
        draft = self.write("draft.md", "Budget: CNY 100")
        report = check_documents(source, [draft])
        self.assertEqual(report["findings"][0]["reason"], "missing_value")
        self.assertEqual(report["coverage"]["compared"], 0)

    def test_a_pipe_in_a_colon_field_value_is_not_a_table(self):
        source = self.write("source.md", "Service scope: A | B")
        draft = self.write("draft.md", "Service scope: A | C")
        report = check_documents(source, [draft])
        self.assertEqual(report["findings"][0]["field"], "Service scope")
        self.assertEqual(report["findings"][0]["reason"], "text_changed")

    def test_fenced_code_and_url_lines_are_unpaired_material(self):
        source = self.write("source.md", "Stage: pilot\n```text\nBudget: CNY 100\n```\nhttps://example.invalid/docs")
        draft = self.write("draft.md", "Stage: pilot\nBudget: CNY 100\nhttps://example.invalid/docs")
        report = check_documents(source, [draft])
        self.assertEqual(report["coverage"]["compared"], 1)
        self.assertEqual(report["coverage"]["unpaired_draft_fields"], ["Budget"])
        self.assertEqual(report["coverage"]["unpaired_prose_blocks"], 3)

    def test_repeated_source_aliases_are_all_visible_and_not_compared(self):
        source = self.write("source.md", "Budget: CNY 1 million\n项目预算：200万元")
        draft = self.write("draft.md", "Budget: CNY 1 million")
        report = check_documents(source, [draft])
        self.assertEqual(report["coverage"]["compared"], 0)
        self.assertEqual({item["reason"] for item in report["findings"]}, {"ambiguous_field"})
        self.assertEqual({item["source"]["value"] for item in report["findings"]},
                         {"CNY 1 million", "200万元"})

    def test_repeated_draft_aliases_require_review_even_if_identical(self):
        source = self.write("source.md", "Stage: pilot")
        draft = self.write("draft.md", "Stage: pilot\n项目阶段：试点")
        report = check_documents(source, [draft])
        self.assertEqual(report["coverage"]["compared"], 0)
        self.assertEqual(len(report["findings"]), 2)
        self.assertTrue(all(item["status"] == "review" for item in report["findings"]))

    def test_coverage_exposes_absent_fields_and_unpaired_prose(self):
        source = self.write("source.md", "Stage: pilot\nOwner: example team\nFree source prose.")
        draft = self.write("draft.md", "Stage: pilot\nAudience: example group\nFree draft prose.")
        report = check_documents(source, [draft])
        self.assertEqual(report["coverage"], {"compared": 1, "source_fields": 2, "draft_fields": 2,
                         "uncompared_source_fields": ["Owner"], "unpaired_draft_fields": ["Audience"],
                         "unpaired_prose_blocks": 2})
        self.assertEqual([item["status"] for item in report["findings"]], ["match"])

    def test_unknown_labels_only_pair_by_normalized_identity(self):
        source = self.write("source.md", "Delivery owner: Example team\nAnnual revenue: CNY 1 million")
        draft = self.write("draft.md", "delivery  owner: example team\nRevenue: CNY 1 million")
        report = check_documents(source, [draft])
        self.assertEqual(report["coverage"]["compared"], 1)
        self.assertEqual(report["coverage"]["unpaired_draft_fields"], ["Revenue"])

    def test_each_draft_is_compared_independently(self):
        source = self.write("source.md", "Stage: pilot")
        drafts = [self.write("a.md", "Stage: pilot"), self.write("b.md", "Stage: deployed")]
        report = check_documents(source, drafts)
        self.assertEqual(report["coverage"]["compared"], 2)
        self.assertEqual([item["status"] for item in report["findings"]], ["match", "review"])

    def test_empty_field_values_are_review_without_coverage(self):
        source = self.write("source.md", "Budget:")
        draft = self.write("draft.md", "Budget:")
        report = check_documents(source, [draft])
        self.assertEqual(report["findings"][0]["reason"], "missing_value")
        self.assertEqual(report["coverage"]["compared"], 0)

    def test_no_corresponding_fields_or_no_drafts_is_input_error(self):
        source = self.write("source.md", "Reference prose has no marked fields.")
        draft = self.write("draft.md", "Draft prose has no marked fields.")
        with self.assertRaises(ValueError):
            check_documents(source, [draft])
        with self.assertRaises(ValueError):
            check_documents(source, [])

    def test_superscript_numbers_cannot_create_false_business_matches(self):
        source = self.write("source.md", "Project budget: USD 10⁶\nService term: 2³ hours")
        draft = self.write("draft.md", "Project budget: USD 106\nService term: 23 hours")
        report = check_documents(source, [draft])
        self.assertEqual([item["status"] for item in report["findings"]], ["review", "review"])
        self.assertEqual({item["reason"] for item in report["findings"]}, {"unsupported_value"})


if __name__ == "__main__":
    unittest.main()
