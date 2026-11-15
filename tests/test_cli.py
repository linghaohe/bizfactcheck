"""Real CLI integration with local synthetic documents; no core mocks."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from bizfactcheck.cli import main


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.write("source.md", "Project budget: CNY 1.2 million\n")
        self.draft = self.write("draft.md", "Project budget: CNY 1200000\n")

    def write(self, name, text):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def run_cli(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        return subprocess.run(
            [sys.executable, "-m", "bizfactcheck", *(str(arg) for arg in args)],
            cwd=self.root, env=env, capture_output=True, text=True, encoding="utf-8", timeout=15,
        )

    def check(self, *options):
        return self.run_cli("check", "--source", self.source, "--draft", self.draft, *options)

    def evidence_check(self):
        return {
            "field": "Project budget", "kind": "money",
            "source": {"path": "source.md", "quote": "Project budget: CNY 1.2 million", "value": "CNY 1.2 million"},
            "draft": {"path": "draft.md", "quote": "Project budget: CNY 1200000", "value": "CNY 1200000"},
        }

    def manifest(self, checks=None):
        if checks is None:
            checks = [self.evidence_check()]
        return self.write("checks.json", json.dumps({"checks": checks}, ensure_ascii=False))

    def test_default_text_report_is_english_and_consistent_exits_zero(self):
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("Business fact check", result.stdout)
        self.assertIn("listed fields", result.stdout)
        self.assertIn("CNY 1200000", result.stdout)
        self.assertIn("line 1", result.stdout)

    def test_multiple_drafts_return_real_conflict_findings_and_exit_one(self):
        other = self.write("other.md", "Project budget: CNY 120 million")
        result = self.run_cli("check", "--source", self.source, "--draft", self.draft, other, "--format", "json")
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["coverage"]["compared"], 2)
        self.assertEqual(report["summary"], {"conflict": 1, "review": 0, "match": 1})
        self.assertEqual({item["draft"]["path"] for item in report["findings"]}, {str(self.draft.resolve()), str(other.resolve())})

    def test_stage_change_is_review_with_one_comparison_and_exit_one(self):
        self.source.write_text("Project stage: pilot", encoding="utf-8")
        self.draft.write_text("Project stage: deployed", encoding="utf-8")
        result = self.check("--format", "json")
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["coverage"]["compared"], 1)
        self.assertEqual(report["findings"][0]["status"], "review")

    def test_all_formats_and_languages_run_through_actual_core(self):
        for language in ("en", "zh"):
            for format in ("text", "json", "md", "html"):
                with self.subTest(language=language, format=format):
                    result = self.check("--lang", language, "--format", format)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stderr, "")
                    if format == "json":
                        self.assertEqual(json.loads(result.stdout)["findings"][0]["status"], "match")
                    else:
                        self.assertIn("Business fact check" if language == "en" else "业务事实核对报告", result.stdout)

    def test_no_labeled_pairs_exits_two_without_claiming_success(self):
        self.source.write_text("A source paragraph without labeled fields.", encoding="utf-8")
        self.draft.write_text("A draft paragraph without labeled fields.", encoding="utf-8")
        result = self.check()
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("comparisons are consistent", result.stdout)

    def test_ambiguous_fields_still_emit_report_with_zero_coverage_and_exit_two(self):
        self.source.write_text("Project budget: CNY 1.2 million\nProject budget: CNY 2 million", encoding="utf-8")
        result = self.check("--format", "json")
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["coverage"]["compared"], 0)
        self.assertGreater(report["summary"]["review"], 0)

    def test_manifest_paths_resolve_relative_to_manifest_and_valid_evidence_exits_zero(self):
        manifest = self.manifest()
        result = self.run_cli("verify", manifest, "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["coverage"]["compared"], 1)
        self.assertEqual(report["findings"][0]["source"]["location"], "line 1")
        self.assertIn(str(manifest.resolve()), report["input_paths"])

    def test_unanchored_manifest_emits_review_report_but_exits_two(self):
        check = self.evidence_check()
        check["draft"]["quote"] = "Project budget: CNY 999 million"
        manifest = self.manifest([check])
        output = self.root / "review.json"
        result = self.run_cli("verify", manifest, "--format", "json", "--output", output)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, "")
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["coverage"]["compared"], 0)
        self.assertEqual(report["findings"][0]["reason"], "quote_not_found")
        self.assertEqual(report["summary"]["review"], 1)

    def test_partial_manifest_with_one_match_and_one_review_exits_one(self):
        valid = self.evidence_check()
        unanchored = copy.deepcopy(valid)
        unanchored["draft"].pop("quote")
        result = self.run_cli("verify", self.manifest([valid, unanchored]), "--format", "json")
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["coverage"]["compared"], 1)
        self.assertEqual(report["summary"], {"conflict": 0, "review": 1, "match": 1})

    def test_invalid_json_and_empty_checks_exit_two_without_dumping_contents(self):
        for content in ('FAKE_PRIVATE_CONTENT is not JSON', '{"checks": []}'):
            with self.subTest(content=content):
                path = self.write("checks.json", content)
                result = self.run_cli("verify", path)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("FAKE_PRIVATE_CONTENT", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_invalid_source_paths_formats_and_encoding_are_input_errors(self):
        unsupported = self.write("source.pdf", "FAKE_PRIVATE_CONTENT")
        empty = self.write("empty.md", "")
        invalid_utf8 = self.root / "bad.md"
        invalid_utf8.write_bytes(b"\xffFAKE_PRIVATE_CONTENT")
        for source in (self.root / "missing.md", self.root, unsupported, empty, invalid_utf8):
            with self.subTest(source=source.name):
                result = self.run_cli("check", "--source", source, "--draft", self.draft)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("FAKE_PRIVATE_CONTENT", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_new_output_file_receives_the_report_without_changing_inputs(self):
        before = (self.source.read_bytes(), self.draft.read_bytes())
        output = self.root / "report.html"
        result = self.check("--lang", "zh", "--format", "html", "--output", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("业务事实核对报告", output.read_text(encoding="utf-8"))
        self.assertEqual((self.source.read_bytes(), self.draft.read_bytes()), before)

    def test_output_never_overwrites_input_existing_report_or_directory(self):
        existing = self.write("report.json", "PRESERVE EXISTING REPORT")
        for output in (self.source, self.draft, existing, self.root):
            with self.subTest(output=output.name):
                before = output.read_bytes() if output.is_file() else None
                result = self.check("--format", "json", "--output", output)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("already exists", result.stderr)
                if before is not None:
                    self.assertEqual(output.read_bytes(), before)

    def test_output_never_overwrites_manifest_or_referenced_inputs(self):
        manifest = self.manifest()
        for output in (manifest, self.source, self.draft):
            with self.subTest(output=output.name):
                before = output.read_bytes()
                result = self.run_cli("verify", manifest, "--output", output)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(output.read_bytes(), before)

    def test_output_rejects_symlinks_including_dangling_links(self):
        for name, target in (("input-link.md", self.source), ("dangling.md", self.root / "not-created.md")):
            with self.subTest(name=name):
                output = self.root / name
                try:
                    output.symlink_to(target)
                except (OSError, NotImplementedError):
                    self.skipTest("symlinks are unavailable")
                before = target.read_bytes() if target.exists() else None
                result = self.check("--output", output)
                self.assertEqual(result.returncode, 2)
                self.assertTrue(output.is_symlink())
                if before is None:
                    self.assertFalse(target.exists())
                else:
                    self.assertEqual(target.read_bytes(), before)

    def test_unwritable_output_does_not_return_success_or_create_parent(self):
        output = self.root / "missing-folder" / "report.json"
        result = self.check("--format", "json", "--output", output)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertFalse(output.parent.exists())
        self.assertNotIn("Traceback", result.stderr)

    def test_main_returns_exit_codes_for_help_and_invalid_arguments_without_echoing_values(self):
        for args, expected in ((["--help"], 0), ([], 2), (["check", "--lang", "FAKE_PRIVATE_CLI_VALUE"], 2)):
            with self.subTest(args=args):
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    result = main(args)
                self.assertEqual(result, expected)
                self.assertNotIn("FAKE_PRIVATE_CLI_VALUE", stderr.getvalue())
                if expected == 0:
                    self.assertIn("check", stdout.getvalue())
                    self.assertIn("verify", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
