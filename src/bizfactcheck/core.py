"""Field and anchored-manifest checks for explicitly selected documents."""

import json
from pathlib import Path
import re
import unicodedata

from . import __version__
from .documents import load_document
from .normalize import KINDS, _QUALIFIERS, compare_values


_LABEL_GROUPS = {
    "project budget": ("money", ["project budget", "budget", "项目预算", "预算"]),
    "revenue": ("money", ["revenue", "营收", "营业收入", "收入"]),
    "reporting period": ("period", ["reporting period", "report period", "报告期间", "报告期", "统计期间"]),
    "project stage": ("status", ["project stage", "stage", "项目阶段", "项目状态"]),
    "service term": ("duration", ["service term", "service duration", "服务期限", "服务期", "服务时长"]),
    "service scope": ("text", ["service scope", "scope of service", "服务范围"]),
}
_ALIASES = {alias: canonical for canonical, (_, aliases) in _LABEL_GROUPS.items() for alias in aliases}


def _label_key(value):
    normalized = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    return _ALIASES.get(normalized, normalized)


def _field_cells(text, location):
    match = re.fullmatch(r"(?:[-*+]\s+)?([^:：\n]{1,80})[:：]\s*(.*)", text, re.DOTALL)
    if not location.startswith("table ") and match and "|" not in match[1]:
        if match[1].casefold() in {"http", "https"} and match[2].startswith("//"):
            return None
        return match.groups()
    if location.startswith("table "):
        cells = text.split("\t")
    elif "|" in text:
        cells = re.split(r"(?<!\\)\|", text)
        if not cells[0].strip():
            cells.pop(0)
        if cells and not cells[-1].strip():
            cells.pop()
    else:
        cells = []
    if cells:
        if len(cells) != 2:
            return None
        cells = [cell.strip() for cell in cells]
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            return ()
        if cells[0].casefold() in {"field", "label", "字段"} and cells[1].casefold() in {"value", "值", "内容"}:
            return ()
        return cells
    return None


def _extract_fields(blocks):
    fields, prose = {}, 0
    fence = None
    for index, block in enumerate(blocks):
        text = block["text"].strip(" \r\n") if block["location"].startswith("table ") else block["text"].strip()
        marker = re.match(r"^(`{3,}|~{3,})", text)
        if marker:
            if fence is None:
                fence = marker[1][0]
            elif marker[1][0] == fence:
                fence = None
            continue
        if fence is not None:
            prose += 1
            continue
        if re.match(r"^#{1,6}\s", text) or re.fullmatch(r"[-*_]{3,}", text):
            continue
        if "|" in text and index + 1 < len(blocks) and re.fullmatch(
                r"\|?\s*:?-{3,}:?\s*\|\s*:?-{3,}:?\s*\|?", blocks[index + 1]["text"]):
            continue
        cells = _field_cells(text, block["location"])
        if cells is None:
            prose += 1
        elif cells:
            label, value = cells
            label = label.strip(" *_`")
            if not label:
                prose += 1
                continue
            evidence = {"path": block["path"], "location": block["location"],
                        "quote": block["text"], "value": value.strip()}
            fields.setdefault(_label_key(label), []).append({"label": label, "evidence": evidence})
    return fields, prose


def _report(mode, paths):
    return {"version": __version__, "mode": mode, "findings": [],
            "coverage": {"compared": 0, "source_fields": 0, "draft_fields": 0,
                         "uncompared_source_fields": [], "unpaired_draft_fields": [],
                         "unpaired_prose_blocks": 0}, "input_paths": list(dict.fromkeys(paths))}


def _finding(field, status, reason, source, draft):
    return {"field": field, "status": status, "reason": reason, "source": source, "draft": draft}


def check_documents(source: Path, drafts: list) -> dict:
    """Compare uniquely paired labeled fields and report the remaining coverage."""
    if not drafts:
        raise ValueError("At least one draft document is required.")
    source, drafts = Path(source).resolve(), [Path(path).resolve() for path in drafts]
    report = _report("check", [str(source)] + [str(path) for path in drafts])
    coverage = report["coverage"]
    source_fields, prose = _extract_fields(load_document(source))
    coverage["source_fields"] = sum(len(entries) for entries in source_fields.values())
    coverage["unpaired_prose_blocks"] = prose
    compared_source = set()
    for path in drafts:
        draft_fields, prose = _extract_fields(load_document(path))
        coverage["draft_fields"] += sum(len(entries) for entries in draft_fields.values())
        coverage["unpaired_prose_blocks"] += prose
        for key, draft_entries in draft_fields.items():
            source_entries = source_fields.get(key, [])
            if not source_entries:
                coverage["unpaired_draft_fields"].extend(entry["label"] for entry in draft_entries)
                continue
            if len(source_entries) > 1 or len(draft_entries) > 1:
                if len(source_entries) > 1:
                    for entry in source_entries:
                        draft = draft_entries[0]["evidence"] if len(draft_entries) == 1 else None
                        report["findings"].append(_finding(entry["label"], "review", "ambiguous_field", entry["evidence"], draft))
                if len(draft_entries) > 1:
                    for entry in draft_entries:
                        ref = source_entries[0]["evidence"] if len(source_entries) == 1 else None
                        report["findings"].append(_finding(entry["label"], "review", "ambiguous_field", ref, entry["evidence"]))
                continue
            first, second = source_entries[0], draft_entries[0]
            kind = _LABEL_GROUPS[key][0] if key in _LABEL_GROUPS else "auto"
            status, reason = compare_values(first["evidence"]["value"], second["evidence"]["value"], kind)
            report["findings"].append(_finding(first["label"], status, reason, first["evidence"], second["evidence"]))
            if first["evidence"]["value"] and second["evidence"]["value"]:
                coverage["compared"] += 1
                compared_source.add(key)
    coverage["uncompared_source_fields"] = [entry["label"] for key, entries in source_fields.items()
                                             if key not in compared_source for entry in entries]
    if not report["findings"]:
        raise ValueError("No corresponding labeled fields were found.")
    return report


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Manifest has duplicate JSON keys.")
        result[key] = value
    return result


def _space(value):
    return " ".join(value.split())


def _occurrences(text, value):
    return [match.start() for match in re.finditer("(?=" + re.escape(value) + ")", text)]


def _boundary_text(text):
    return unicodedata.normalize("NFKC", text).casefold().translate(str.maketrans("−–—", "---"))


def _complete_span(text, start, end):
    """Reject fragments of tokens and supported quantity expressions in the original text."""
    prefix, value, suffix = (_boundary_text(text[:start]), _boundary_text(text[start:end]),
                             _boundary_text(text[end:]))
    before, after = prefix[-1:], suffix[:1]
    if re.match(r"[a-z0-9_]", value[0]) and re.match(r"[a-z0-9_]", before):
        return False
    if re.match(r"[a-z0-9_]", value[-1]) and re.match(r"[a-z0-9_]", after):
        return False
    if value[0].isdigit() and before in {".", ",", "+", "-"}:
        return False
    if value[-1].isdigit() and after in {".", ","} and suffix[1:2].isdigit():
        return False
    if not any(char.isdigit() for char in value):
        return True
    if re.match(r"[+-]?[0-9]|cny|rmb|usd|人民币|美元", value) and re.search(
            r"(?:[+-]|\b(?:cny|rmb|usd|h[12]|q[1-4])|人民币|美元|[$¥])\s*$", prefix):
        return False
    if value[-1] not in ".。!！?？;；,:：" and re.match(
            r"\s*(?:(?:thousand|million|billion|cny|rmb|usd|dollars?|percent|percentage|pp|"
            r"minutes?|hours?|days?|months?|years?|min|hr)\b|"
            r"元|万|亿|美元|人民币|分钟|小时|天|日|个月|月|年|个百分点|%|"
            r"上半年|下半年|第?[一二三四1-4]季度|[hq][1-4]|"
            r"(?:/|per\b|a\b|each\b|每)\s*(?:(?:minutes?|hours?|days?|months?|years?)\b|分钟|小时|天|日|月|年))",
            suffix):
        return False
    return True


def _value_occurrences(quote, value):
    return [start for start in _occurrences(quote, value) if _complete_span(quote, start, start + len(value))]


def _qualified_context(text, start, end):
    """Check supported modifiers outside the value in its original clause."""
    before = re.split(r"[.!?;。！？；]", _boundary_text(text[:start]))[-1]
    after = re.split(r"[.!?;。！？；]", _boundary_text(text[end:]))[0]
    value = _boundary_text(text[start:end])
    for match in _QUALIFIERS.finditer(before + value + after):
        if match.start() < len(before) or match.end() > len(before) + len(value):
            return True
    negative = r"\b(?:not|never|no|cannot)\b|\b[a-z]+n['’]t\b|未|没有|并非|不是|不曾|不能|不支持|不提供|不包含"
    return bool(re.search(negative, before) or re.search(negative, after))


def _anchor(raw, base, documents, input_paths, anchored_blocks):
    if not isinstance(raw, dict):
        return None, "missing_evidence", False
    evidence = {"path": "", "location": "", "quote": raw.get("quote", ""), "value": raw.get("value", "")}
    for key in ("quote", "value"):
        if not isinstance(evidence[key], str):
            evidence[key] = ""
    if not isinstance(raw.get("path"), str) or not raw["path"].strip():
        return evidence, "missing_path", False
    path = (base / raw["path"]).resolve()
    evidence["path"] = str(path)
    if str(path) not in input_paths:
        input_paths.append(str(path))
    if path not in documents:
        documents[path] = load_document(path)
    blocks = documents[path]
    quote, value = _space(evidence["quote"]), _space(evidence["value"])
    if not quote:
        return evidence, "missing_quote", False
    if not value:
        return evidence, "missing_value", False
    normalized = [_space(block["text"]) for block in blocks]
    text = " ".join(normalized)
    positions = _occurrences(text, quote)
    if not positions:
        return evidence, "quote_not_found", False
    if len(positions) > 1:
        return evidence, "ambiguous_quote", False
    start, end = positions[0], positions[0] + len(quote)
    if not _complete_span(text, start, end):
        return evidence, "incomplete_quote", False
    value_positions = _value_occurrences(quote, value)
    if not value_positions:
        return evidence, "value_not_in_quote", False
    if len(value_positions) > 1:
        return evidence, "ambiguous_value", False
    value_start = start + value_positions[0]
    if not _complete_span(text, value_start, value_start + len(value)):
        return evidence, "value_not_in_quote", False
    offset, locations = 0, []
    for index, content in enumerate(normalized):
        if offset < end and offset + len(content) > start:
            locations.append(blocks[index]["location"])
            anchored_blocks.add((path, index))
        offset += len(content) + 1
    evidence["location"] = locations[0] if len(locations) == 1 else locations[0] + " - " + locations[-1]
    return evidence, None, _qualified_context(text, value_start, value_start + len(value))


def verify_manifest(path: Path) -> dict:
    """Verify literal anchors before comparing each manifest-selected value pair."""
    path = Path(path).resolve()
    if path.suffix.lower() != ".json":
        raise ValueError("A manifest must be a .json file.")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("Manifest must contain valid UTF-8 JSON.") from None
    except OSError:
        raise OSError("Unable to read the manifest file.") from None
    if not isinstance(data, dict) or not isinstance(data.get("checks"), list) or not data["checks"]:
        raise ValueError("Manifest must contain a nonempty checks list.")
    for check in data["checks"]:
        if not isinstance(check, dict) or not isinstance(check.get("field"), str) or not check["field"].strip():
            raise ValueError("Every manifest check needs a nonempty field name.")
        if not isinstance(check.get("kind", "auto"), str) or check.get("kind", "auto") not in KINDS:
            raise ValueError("Unsupported comparison kind in manifest.")
    report = _report("verify", [str(path)])
    coverage = report["coverage"]
    coverage["source_fields"] = coverage["draft_fields"] = len(data["checks"])
    documents, anchored_blocks = {}, set()
    for check in data["checks"]:
        source, source_error, source_qualified = _anchor(check.get("source"), path.parent, documents, report["input_paths"], anchored_blocks)
        draft, draft_error, draft_qualified = _anchor(check.get("draft"), path.parent, documents, report["input_paths"], anchored_blocks)
        reason = source_error or draft_error
        if reason:
            status = "review"
            coverage["uncompared_source_fields"].append(check["field"])
            coverage["unpaired_draft_fields"].append(check["field"])
        else:
            kind = check.get("kind", "auto")
            status, reason = compare_values(source["value"], draft["value"], kind)
            if source_qualified or draft_qualified:
                status, reason = "review", "qualified_value"
            coverage["compared"] += 1
        report["findings"].append(_finding(check["field"], status, reason, source, draft))
    coverage["unpaired_prose_blocks"] = sum(len(blocks) for blocks in documents.values()) - len(anchored_blocks)
    return report
