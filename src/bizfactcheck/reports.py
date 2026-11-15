"""Bilingual, offline reports for the core's explicit comparisons."""

from html import escape
import json
import re


_COPY = {
    "en": {
        "title": "Business fact check",
        "subtitle": "Compare business claims with the references you selected.",
        "check": "Labeled field check",
        "verify": "Evidence manifest check",
        "scope": "Only the listed fields are compared with the selected references. This is not a full-document fact check.",
        "empty": "No comparable pairs. Review the inputs and coverage before relying on this report.",
        "attention": "Differences or unresolved evidence need review.",
        "clean": "The listed comparisons are consistent with the selected references.",
        "conflict": "Differences", "review": "Needs review", "match": "Consistent",
        "compared": "Compared pairs", "coverage": "Coverage", "findings": "Findings",
        "source_fields": "Reference fields", "draft_fields": "Draft fields",
        "uncompared_source_fields": "Reference fields not compared",
        "unpaired_draft_fields": "Unpaired draft fields",
        "unpaired_prose_blocks": "Unpaired prose blocks",
        "source": "Reference", "draft": "Draft", "value": "Value",
        "path": "File", "location": "Location", "quote": "Original quote",
        "explanation": "Explanation", "none": "None", "missing": "Not provided",
        "no_findings": "No field findings are available.", "limitations": "Limits of this report",
        "limitations_text": [
            "A consistent result applies only to the comparisons shown. Unpaired fields and prose may contain other claims.",
            "DOCX extraction covers body paragraphs and tables only; headers, footers, text boxes and tracked changes are outside its scope. PDF/OCR, spreadsheets and slides are not supported.",
            "This report does not establish factual truth, legal compliance, real deployment or business acceptance. Confirm the reference and business context with the responsible owner.",
        ],
        "manifest_limit": "Quotes anchor values to document text; human review is still needed to confirm the semantic pairing and scope of each claim.",
        "fallback": "This comparison needs human review before a conclusion can be drawn.",
    },
    "zh": {
        "title": "业务事实核对报告",
        "subtitle": "将业务表述与您选定的参考材料逐项核对。",
        "check": "标注字段核对", "verify": "证据清单核对",
        "scope": "仅核对列出的字段及所选参考材料，不代表完成全文事实核查。",
        "empty": "没有可比较的字段对。请先检查输入和覆盖范围，再使用本报告。",
        "attention": "发现差异或证据尚不充分的项目，需要复核。",
        "clean": "列出的比较项与所选参考材料一致。",
        "conflict": "差异", "review": "待复核", "match": "一致",
        "compared": "已比较字段对", "coverage": "覆盖范围", "findings": "逐项结果",
        "source_fields": "参考材料字段", "draft_fields": "待核稿字段",
        "uncompared_source_fields": "未比较的参考字段", "unpaired_draft_fields": "未配对的待核稿字段",
        "unpaired_prose_blocks": "未配对的正文块",
        "source": "参考材料", "draft": "待核稿", "value": "值", "path": "文件",
        "location": "位置", "quote": "原文", "explanation": "说明",
        "none": "无", "missing": "未提供", "no_findings": "没有可展示的字段结果。",
        "limitations": "使用边界",
        "limitations_text": [
            "一致结论仅适用于本报告列出的比较项。未配对字段和正文中仍可能存在其他表述。",
            "DOCX 仅读取正文段落和表格，不覆盖页眉、页脚、文本框及修订记录；不支持 PDF/OCR、电子表格和幻灯片。",
            "本报告不能证明事实真实、法律合规、已经实际部署或完成业务验收。请向责任人确认参考材料及业务语境。",
        ],
        "manifest_limit": "引文仅用于定位文档中的值，表述之间是否在语义和范围上正确配对，仍需人工复核。",
        "fallback": "此比较项需要人工复核，暂不能作出结论。",
    },
}

_REASONS = {
    "equivalent_value": ("The supported values are equivalent after normalization.", "按支持的单位和格式归一化后，两项数值一致。"),
    "equal_text": ("The compared text is consistent after formatting normalization.", "归一化格式后，两项文本一致。"),
    "different_value": ("The values differ within the same supported type and unit basis.", "两项属于相同的受支持类型和单位口径，但数值不同。"),
    "currency_mismatch": ("The currencies differ; no currency conversion was performed.", "币种不同，未执行汇率换算，需要确认口径。"),
    "unit_mismatch": ("The units cannot be safely compared under the supported conversion rules.", "现有换算规则无法安全比较这两种单位，需要确认口径。"),
    "qualified_value": ("A qualifier or inequality changes the claim; confirm its intended meaning.", "表述含限定词或不等号，需要确认其实际含义。"),
    "unsupported_value": ("The value is outside the supported normalization rules.", "该值不在支持的归一化规则内，需要人工核对。"),
    "type_mismatch": ("The values were recognized as different types; confirm that they describe the same fact.", "两项被识别为不同类型，需要确认是否描述同一事实。"),
    "stage_changed": ("The project stages differ; confirm the status and reporting context.", "项目阶段不同，需要确认当前状态和报告语境。"),
    "text_changed": ("The wording differs; human review is needed to assess whether the meaning changed.", "文本表述不同，需要人工判断含义是否变化。"),
    "missing_value": ("A comparison value is missing; supply it before drawing a conclusion.", "缺少比较值，补充后才能作出结论。"),
    "ambiguous_field": ("A field appears more than once or has ambiguous matches; identify the intended pair.", "字段重复或匹配关系不明确，需要指定应比较的两项。"),
    "missing_evidence": ("The evidence record is missing or incomplete.", "证据记录缺失或不完整，需要补充。"),
    "missing_path": ("An evidence file path is missing; identify the source document.", "证据文件路径缺失，需要指定原始文档。"),
    "missing_quote": ("An evidence quote is missing; provide the supporting document text.", "证据引文缺失，需要提供对应原文。"),
    "quote_not_found": ("The quoted evidence was not found in the specified document.", "在指定文档中未找到该引文，需要核对原文和路径。"),
    "ambiguous_quote": ("The quote has multiple document matches; provide a more specific excerpt.", "引文在文档中出现多次，需要补充更明确的上下文。"),
    "value_not_in_quote": ("The literal value does not occur in the supplied quote.", "声明的值未按原样出现在所提供的引文中。"),
    "ambiguous_value": ("The value occurs ambiguously in its evidence; clarify the intended claim.", "证据中的值无法唯一对应到目标表述，需要补充说明。"),
    "incomplete_quote": ("The quote may truncate a complete value, unit or reporting period; quote the full sentence for review.", "引文可能截掉了完整数值、单位或期间；请引用完整原句后复核。"),
}

_CSS = """
:root{color-scheme:light;--ink:#182a42;--muted:#55657a;--line:#dce4ee;--paper:#fff}
*{box-sizing:border-box}body{margin:0;background:#f3f6fb;color:var(--ink);font:16px/1.6 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
main{max-width:1120px;margin:auto;padding:48px 28px 60px}header{margin-bottom:28px}.brand{font-size:12px;font-weight:750;letter-spacing:.16em;color:#32647c}
h1{font-size:36px;line-height:1.2;margin:12px 0}h2{font-size:22px;margin:32px 0 14px}h3{font-size:18px;margin:0;overflow-wrap:anywhere}
p{margin:8px 0}.muted,.meta{color:var(--muted)}.meta{font-size:13px}.outcome{font-size:18px;font-weight:650;margin-top:18px}
.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:24px 0}.metric{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:18px}.metric strong{display:block;font-size:32px;line-height:1.2}.metric span{color:var(--muted);font-size:14px}
.scope{background:#eaf2f8;border-left:4px solid #32647c;padding:14px 18px;border-radius:4px}.coverage{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:20px}.coverage dl{display:grid;grid-template-columns:minmax(200px,1fr) 2fr;gap:10px 24px;margin:0}.coverage dt{color:var(--muted)}.coverage dd{margin:0;overflow-wrap:anywhere}
.finding{background:var(--paper);border:1px solid var(--line);border-left:4px solid #7b8796;border-radius:10px;padding:22px;margin:14px 0;break-inside:avoid}.finding.conflict{border-left-color:#b43b32}.finding.review{border-left-color:#a36712}.finding.match{border-left-color:#217052}.finding-head{display:flex;justify-content:space-between;align-items:flex-start;gap:18px}.badge{white-space:nowrap;border-radius:30px;font-size:12px;font-weight:700;padding:4px 11px;background:#e9eef4;color:#405168}.conflict .badge{background:#fbe9e6;color:#952e29}.review .badge{background:#fff1d8;color:#805010}.match .badge{background:#e5f3ec;color:#175e43}
.explanation{margin:12px 0 18px;color:var(--muted)}.evidence-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.evidence{min-width:0;background:#f8fafc;border:1px solid #e5ebf1;border-radius:8px;padding:16px}.evidence h4{font-size:13px;color:#48617a;margin:0 0 8px}.value{font-size:18px;font-weight:650;white-space:pre-wrap;overflow-wrap:anywhere}.location{font-size:12px;color:var(--muted);overflow-wrap:anywhere;margin:10px 0}.quote-label{font-size:12px;color:var(--muted)}blockquote{margin:4px 0 0;padding-left:12px;border-left:2px solid #cad7e5;font-size:14px;white-space:pre-wrap;overflow-wrap:anywhere}
.limits{font-size:14px;color:var(--muted);border-top:1px solid var(--line);margin-top:32px;padding-top:2px}.limits li{margin:9px 0}footer{font-size:12px;color:var(--muted);margin-top:28px}
@media(max-width:720px){main{padding:28px 16px}h1{font-size:28px}.summary{grid-template-columns:repeat(2,1fr)}.evidence-grid{grid-template-columns:1fr}.coverage dl{grid-template-columns:1fr;gap:2px}.coverage dd{margin-bottom:12px}.finding{padding:16px}}
@media print{body{background:#fff}main{padding:0;max-width:none}.finding,.coverage,.metric{box-shadow:none}h2{break-after:avoid}}
"""


def _explanation(reason, lang):
    pair = _REASONS.get(reason)
    return pair[lang == "zh"] if pair else _COPY[lang]["fallback"]


def _outcome(report, copy):
    if not report["coverage"]["compared"]:
        return copy["empty"]
    if report["summary"]["conflict"] or report["summary"]["review"]:
        return copy["attention"]
    return copy["clean"]


def _coverage_rows(report, copy):
    coverage = report["coverage"]
    rows = []
    for key in ("source_fields", "draft_fields", "uncompared_source_fields", "unpaired_draft_fields", "unpaired_prose_blocks"):
        value = coverage[key]
        if isinstance(value, list):
            value = "; ".join(value) or copy["none"]
        rows.append((copy[key], str(value)))
    return rows


def _md(value):
    text = escape(str(value), quote=True)
    text = re.sub(r"([\\`*_{}\[\]()#|~])", r"\\\1", text)
    return text.replace("\n", "<br>")


def _text_report(report, copy, markdown):
    safe = _md if markdown else str
    title = copy["title"]
    lines = [f"# {title}" if markdown else f"BizFactCheck — {title}"]
    lines += ["", safe(copy[report["mode"]]), "", safe(_outcome(report, copy)), ""]
    metrics = [(copy["compared"], report["coverage"]["compared"])]
    metrics += [(copy[key], report["summary"][key]) for key in ("conflict", "review", "match")]
    lines.append(" | ".join(f"{label}: {value}" for label, value in metrics))
    lines += ["", safe(report["scope"]), "", ("## " if markdown else "") + copy["coverage"]]
    lines += [f"{label}: {safe(value)}" + ("  " if markdown else "") for label, value in _coverage_rows(report, copy)]
    lines += ["", ("## " if markdown else "") + copy["findings"]]
    if not report["findings"]:
        lines.append(copy["no_findings"])
    for index, finding in enumerate(report["findings"], 1):
        label = copy[finding["status"]]
        heading = f"{index}. {safe(finding['field'])} — {label}"
        lines += ["", ("### " if markdown else "") + heading, "", safe(finding["explanation"])]
        for side in ("source", "draft"):
            lines += ["", f"**{copy[side]}**" if markdown else copy[side]]
            evidence = finding[side]
            if evidence is None:
                lines.append(copy["missing"])
                continue
            for key in ("value", "path", "location", "quote"):
                value = evidence.get(key) or copy["missing"]
                lines.append(f"{copy[key]}: {safe(value)}" + ("  " if markdown else ""))
    lines += ["", ("## " if markdown else "") + copy["limitations"]]
    lines += ["- " + safe(item) for item in report["limitations"]]
    return "\n".join(lines)


def _html_report(report, copy, lang):
    def safe(value):
        return escape(str(value), quote=True)

    parts = [
        '<!doctype html>', f'<html lang="{"zh-CN" if lang == "zh" else "en"}">',
        '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>BizFactCheck — {copy["title"]}</title><style>{_CSS}</style></head><body><main>',
        '<header><div class="brand">BIZFACTCHECK</div>',
        f'<h1>{copy["title"]}</h1><p class="muted">{copy["subtitle"]}</p>',
        f'<p class="meta">{copy[report["mode"]]} · v{safe(report["version"])}</p>',
        f'<p class="outcome">{_outcome(report, copy)}</p></header><div class="summary">',
    ]
    metrics = [(copy["compared"], report["coverage"]["compared"])]
    metrics += [(copy[key], report["summary"][key]) for key in ("conflict", "review", "match")]
    for label, value in metrics:
        parts.append(f'<div class="metric"><strong>{safe(value)}</strong><span>{label}</span></div>')
    parts += ['</div>', f'<p class="scope">{safe(report["scope"])}</p>',
              f'<section><h2>{copy["coverage"]}</h2><div class="coverage"><dl>']
    for label, value in _coverage_rows(report, copy):
        parts.append(f'<dt>{label}</dt><dd>{safe(value)}</dd>')
    parts += ['</dl></div></section>', f'<section><h2>{copy["findings"]}</h2>']
    if not report["findings"]:
        parts.append(f'<p class="muted">{copy["no_findings"]}</p>')
    for index, finding in enumerate(report["findings"], 1):
        status = finding["status"]
        parts += [
            f'<article class="finding {safe(status)}"><div class="finding-head">',
            f'<h3>{index}. {safe(finding["field"])}</h3><span class="badge">{copy[status]}</span></div>',
            f'<p class="explanation">{safe(finding["explanation"])}</p><div class="evidence-grid">',
        ]
        for side in ("source", "draft"):
            parts.append(f'<section class="evidence"><h4>{copy[side]}</h4>')
            evidence = finding[side]
            if evidence is None:
                parts.append(f'<p>{copy["missing"]}</p>')
            else:
                value, path, location, quote = [safe(evidence.get(key) or copy["missing"]) for key in ("value", "path", "location", "quote")]
                parts += [f'<div class="value">{value}</div>',
                          f'<div class="location">{copy["path"]}: {path}<br>{copy["location"]}: {location}</div>',
                          f'<div class="quote-label">{copy["quote"]}</div><blockquote>{quote}</blockquote>']
            parts.append('</section>')
        parts.append('</div></article>')
    parts += ['</section>', f'<section class="limits"><h2>{copy["limitations"]}</h2><ul>']
    parts += [f'<li>{safe(item)}</li>' for item in report["limitations"]]
    parts += ['</ul></section><footer>BizFactCheck · ' + safe(report["version"]) + '</footer></main></body></html>']
    return "\n".join(parts)


def render_report(report: dict, lang: str = "en", format: str = "text") -> str:
    """Render a core report without mutating it or translating machine keys."""
    if lang not in _COPY or format not in ("text", "json", "md", "html"):
        raise ValueError("Unsupported report language or format")
    copy = _COPY[lang]
    summary = {status: sum(finding["status"] == status for finding in report["findings"]) for status in ("conflict", "review", "match")}
    limitations = list(copy["limitations_text"])
    if report["mode"] == "verify":
        limitations.append(copy["manifest_limit"])
    result = {
        **report,
        "findings": [{**finding, "explanation": _explanation(finding["reason"], lang)} for finding in report["findings"]],
        "summary": summary,
        "scope": copy["scope"],
        "limitations": limitations,
    }
    if format == "json":
        return json.dumps(result, ensure_ascii=False, indent=2)
    if format == "html":
        return _html_report(result, copy, lang)
    return _text_report(result, copy, format == "md")
