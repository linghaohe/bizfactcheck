"""Read only supported local document content."""

from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_OMIT = {_W + tag for tag in ("ins", "del", "moveFrom", "moveTo", "txbxContent")}


def _paragraph_text(node):
    if node.tag in _OMIT:
        return ""
    if node.tag == _W + "t":
        return node.text or ""
    if node.tag == _W + "tab":
        return "\t"
    if node.tag in {_W + "br", _W + "cr"}:
        return "\n"
    return "".join(_paragraph_text(child) for child in node)


def _docx_blocks(path):
    try:
        with zipfile.ZipFile(path) as package:
            xml = package.read("word/document.xml")
        if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
            raise ValueError("DOCX XML declarations are unsupported.")
        root = ET.fromstring(xml)
    except (zipfile.BadZipFile, KeyError, ET.ParseError, RuntimeError, NotImplementedError):
        raise ValueError("Invalid or unsupported DOCX document.") from None
    body = root.find(_W + "body")
    if root.tag != _W + "document" or body is None:
        raise ValueError("DOCX document has no supported body.")
    blocks = []
    paragraph, table = 0, 0
    for node in body:
        if node.tag == _W + "p":
            paragraph += 1
            text = _paragraph_text(node).strip()
            if text:
                blocks.append({"path": str(path), "location": "paragraph {}".format(paragraph), "text": text})
        elif node.tag == _W + "tbl":
            table += 1
            for row_number, row in enumerate(node.findall(_W + "tr"), 1):
                cells = [" ".join(_paragraph_text(p).strip() for p in cell.findall(_W + "p"))
                         for cell in row.findall(_W + "tc")]
                if any(cell.strip() for cell in cells):
                    blocks.append({"path": str(path), "location": "table {} row {}".format(table, row_number),
                                   "text": "\t".join(cells)})
    return blocks


def load_document(path: Path) -> list:
    """Read UTF-8 text or DOCX body paragraphs/tables; never execute content."""
    path = Path(path).resolve()
    if path.suffix.lower() not in {".md", ".txt", ".docx"}:
        raise ValueError("Unsupported document format. Use .md, .txt, or .docx.")
    try:
        if path.suffix.lower() == ".docx":
            blocks = _docx_blocks(path)
        else:
            content = path.read_text(encoding="utf-8-sig")
            blocks = [{"path": str(path), "location": "line {}".format(number), "text": line.strip()}
                      for number, line in enumerate(content.splitlines(), 1) if line.strip()]
    except UnicodeError:
        raise ValueError("Text documents must use UTF-8 encoding.") from None
    except OSError:
        raise OSError("Unable to read an input document.") from None
    if not blocks:
        raise ValueError("Document has no readable supported text.")
    return blocks
