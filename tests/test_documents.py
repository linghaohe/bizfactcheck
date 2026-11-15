import tempfile
import unittest
import zipfile
from pathlib import Path

from bizfactcheck.documents import load_document


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, content):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def docx(self, body):
        path = self.root / "sample.docx"
        with zipfile.ZipFile(path, "w") as package:
            package.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
            package.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
            package.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + body + '</w:body></w:document>')
            package.writestr("word/header1.xml", "HEADER MUST NOT BE READ")
        return path

    def test_utf8_blocks_retain_real_line_locations(self):
        path = self.write("source.md", "\ufeff项目预算：120万元\n\nStage: pilot\n")
        self.assertEqual(load_document(path), [
            {"path": str(path.resolve()), "location": "line 1", "text": "项目预算：120万元"},
            {"path": str(path.resolve()), "location": "line 3", "text": "Stage: pilot"},
        ])

    def test_docx_reads_body_paragraphs_and_table_rows_in_order(self):
        path = self.docx('<w:p><w:r><w:t>Stage: </w:t></w:r><w:r><w:t>pilot</w:t></w:r></w:p>'
                         '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Budget</w:t></w:r></w:p></w:tc>'
                         '<w:tc><w:p><w:r><w:t>CNY 1 million</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
                         '<w:p><w:r><w:t>Scope: support</w:t></w:r></w:p>')
        blocks = load_document(path)
        self.assertEqual([block["text"] for block in blocks],
                         ["Stage: pilot", "Budget\tCNY 1 million", "Scope: support"])
        self.assertEqual([block["location"] for block in blocks],
                         ["paragraph 1", "table 1 row 1", "paragraph 2"])
        self.assertTrue(all(block["path"] == str(path.resolve()) for block in blocks))

    def test_docx_omits_unsupported_tracked_changes_and_text_boxes(self):
        path = self.docx('<w:p><w:r><w:t>Visible</w:t></w:r>'
                         '<w:del><w:r><w:delText> deleted</w:delText></w:r></w:del>'
                         '<w:ins><w:r><w:t> inserted</w:t></w:r></w:ins>'
                         '<w:r><w:txbxContent><w:p><w:r><w:t> text box</w:t></w:r></w:p></w:txbxContent></w:r></w:p>')
        self.assertEqual([block["text"] for block in load_document(path)], ["Visible"])

    def test_empty_and_invalid_utf8_files_are_input_errors(self):
        for name, content in [("empty.txt", b" \n\t"), ("broken.txt", b"\xff\xfe")]:
            with self.subTest(name=name):
                path = self.root / name
                path.write_bytes(content)
                with self.assertRaises(ValueError):
                    load_document(path)

    def test_missing_files_and_directories_raise_oserror(self):
        with self.assertRaises(OSError):
            load_document(self.root / "missing.md")
        directory = self.root / "folder.md"
        directory.mkdir()
        with self.assertRaises(OSError):
            load_document(directory)

    def test_unsupported_formats_and_env_symlinks_are_rejected(self):
        for name in ["input.pdf", "input.xlsx", ".env", "input.json"]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    load_document(self.write(name, "SYNTHETIC_INPUT"))
        link = self.root / "disguised.md"
        try:
            link.symlink_to(self.root / ".env")
        except (OSError, NotImplementedError):
            self.skipTest("This platform does not allow test symlinks")
        with self.assertRaises(ValueError):
            load_document(link)

    def test_invalid_docx_zip_xml_and_missing_body_are_input_errors(self):
        path = self.write("invalid.docx", "not a zip")
        with self.assertRaises(ValueError):
            load_document(path)
        for xml in ["<broken", "<document />"]:
            with self.subTest(xml=xml):
                with zipfile.ZipFile(path, "w") as package:
                    package.writestr("word/document.xml", xml)
                with self.assertRaises(ValueError):
                    load_document(path)
        with zipfile.ZipFile(path, "w") as package:
            package.writestr("unrelated.xml", "<document />")
        with self.assertRaises(ValueError):
            load_document(path)


if __name__ == "__main__":
    unittest.main()
