"""Conservative comparisons of explicit business values."""

import re
import unicodedata
from decimal import Decimal, localcontext


KINDS = frozenset({"auto", "money", "duration", "percentage", "period", "status", "text"})
_NUMBER = r"[+-]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?"
_CURRENCIES = {"cny": "CNY", "rmb": "CNY", "人民币": "CNY", "元": "CNY",
               "usd": "USD", "dollar": "USD", "dollars": "USD", "美元": "USD"}
_SCALES = {None: 1, "thousand": 1000, "million": 1000000,
           "billion": 1000000000, "万": 10000, "亿": 100000000}
_MONEY = re.compile(
    r"(?:(cny|rmb|人民币|usd|美元)\s*)?(" + _NUMBER + r")\s*"
    r"(thousand|million|billion|万|亿)?\s*(cny|rmb|人民币|usd|dollars?|元|美元)?"
)
_DURATION_UNITS = {
    "minute": ("minutes", 1), "minutes": ("minutes", 1), "min": ("minutes", 1),
    "分钟": ("minutes", 1), "hour": ("minutes", 60), "hours": ("minutes", 60),
    "hr": ("minutes", 60), "小时": ("minutes", 60), "day": ("minutes", 1440),
    "days": ("minutes", 1440), "天": ("minutes", 1440), "日": ("minutes", 1440),
    "month": ("months", 1), "months": ("months", 1), "月": ("months", 1),
    "个月": ("months", 1), "year": ("months", 12), "years": ("months", 12),
    "年": ("months", 12),
}
_STAGES = {
    "planned": "planned", "计划": "planned", "计划中": "planned", "规划中": "planned",
    "prototype": "prototype", "原型": "prototype", "研究原型": "prototype",
    "pilot": "pilot", "试点": "pilot", "试点中": "pilot", "已试点": "pilot",
    "deployed": "deployed", "已部署": "deployed", "正式上线": "deployed", "已上线": "deployed",
    "accepted": "accepted", "已验收": "accepted", "验收通过": "accepted",
}
_QUALIFIERS = re.compile(
    r"[<>=≤≥≈±~]|\b(?:about|approximately|approx\.?|roughly|estimated|around|"
    r"at least|at most|up to|less than|greater than|more than|no more than|"
    r"minimum|maximum|over|under)\b|大约|约(?:为|计|合)?(?=\s*(?:[+-]?[0-9]|cny|rmb|usd|人民币|美元|[$¥]))|"
    r"预计|估计|至少|至多|超过|不少于|不低于|"
    r"低于|大于|小于|以上|以下|以内"
)


def _clean(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _has_qualifier(value):
    return bool(_QUALIFIERS.search(_clean(value)))


def _scaled(number, factor):
    number = number.replace(",", "")
    with localcontext() as context:
        context.prec = max(28, len(number) + 12)
        return Decimal(number) * Decimal(factor)


def _money(value):
    match = _MONEY.fullmatch(value)
    if not match:
        return None
    prefix, number, scale, suffix = match.groups()
    first, second = _CURRENCIES.get(prefix), _CURRENCIES.get(suffix)
    if not (first or second) or (first and second and first != second):
        return None
    return "money", first or second, _scaled(number, _SCALES[scale])


def _duration(value):
    match = re.fullmatch(r"(" + _NUMBER + r")\s*(.+)", value)
    if not match or match[2] not in _DURATION_UNITS:
        return None
    unit, scale = _DURATION_UNITS[match[2]]
    return "duration", unit, _scaled(match[1], scale)


def _percentage(value):
    match = re.fullmatch(r"(" + _NUMBER + r")\s*(%|percent|percentage points?|pp|个百分点)", value)
    if not match:
        return None
    unit = "percent" if match[2] in {"%", "percent"} else "percentage_points"
    return "percentage", unit, _scaled(match[1], 1)


def _period(value):
    compact = value.replace(" ", "")
    match = re.fullmatch(r"([1-9][0-9]{3})(?:年|年度|全年|年全年)?", compact)
    if match:
        return "period", "calendar", (match[1], "year", 0)
    match = re.fullmatch(r"([1-9][0-9]{3})年?(h[12]|q[1-4]|上半年|下半年|第?[一二三四1-4]季度)", compact)
    if match:
        year, part = match.groups()
    else:
        match = re.fullmatch(r"(h[12]|q[1-4])([1-9][0-9]{3})", compact)
        if not match:
            return None
        part, year = match.groups()
    if part in {"上半年", "下半年"}:
        part = "h1" if part == "上半年" else "h2"
    elif "季度" in part:
        number = part.removeprefix("第").removesuffix("季度")
        part = "q" + dict(zip("一二三四", "1234")).get(number, number)
    return "period", "calendar", (year, part[0], int(part[1]))


def _status(value):
    if value in _STAGES:
        return "status", "stage", _STAGES[value]
    return None


_PARSERS = {"money": _money, "period": _period, "duration": _duration,
            "percentage": _percentage, "status": _status}


def _parse(value, kind):
    if kind != "auto":
        return _PARSERS[kind](value)
    for parser in _PARSERS.values():
        result = parser(value)
        if result is not None:
            return result
    return None


def _looks_numeric(value):
    return bool(re.search(r"[0-9$¥€%]|\b(?:cny|rmb|usd|nan|infinity)\b|人民币|美元|万元|亿元", value))


def compare_values(source: str, draft: str, kind: str = "auto") -> tuple:
    """Return (match/conflict/review, stable reason), without guessing meaning."""
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError("Unsupported comparison kind.")
    if not isinstance(source, str) or not isinstance(draft, str):
        raise ValueError("Comparison values must be strings.")
    for value in (source, draft):
        if any(char.isnumeric() and not "０" <= char <= "９"
               and unicodedata.normalize("NFKC", char) != char for char in value):
            return "review", "unsupported_value"
    source, draft = _clean(source), _clean(draft)
    if not source or not draft:
        return "review", "missing_value"
    if kind == "text":
        return ("match", "equal_text") if source == draft else ("review", "text_changed")
    if _has_qualifier(source) or _has_qualifier(draft):
        return "review", "qualified_value"
    first, second = _parse(source, kind), _parse(draft, kind)
    if first is None or second is None:
        if kind != "auto" or first is not None or second is not None or _looks_numeric(source) or _looks_numeric(draft):
            return "review", "unsupported_value"
        return ("match", "equal_text") if source == draft else ("review", "text_changed")
    if first[0] != second[0]:
        return "review", "type_mismatch"
    if first[1] != second[1]:
        return "review", "currency_mismatch" if first[0] == "money" else "unit_mismatch"
    if first[2] == second[2]:
        return "match", "equivalent_value"
    if first[0] == "status":
        return "review", "stage_changed"
    return "conflict", "different_value"
