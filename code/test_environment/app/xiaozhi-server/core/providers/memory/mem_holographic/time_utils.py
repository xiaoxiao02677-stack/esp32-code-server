"""Time-reference extraction utilities for holographic memory.

Maps user utterances containing temporal cues into structured ``time_reference``
strings stored alongside each fact. The references are consumed by the
timeline query endpoints on the memory handler.
"""
import re
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Pattern库：中文时间表达 -> 结构化引用
# ---------------------------------------------------------------------------

# 相对时间映射（相对于 now）
_RELATIVE_MAP = {
    "昨天": -1, "前天": -2,
    "明天": 1, "后天": 2,
    "大后天": 3, "大前天": -3,
    "今天": 0,
    "刚才": 0, "刚刚": 0,
}

# 周期性关键词
_RECURRING_PATTERNS = [
    (re.compile(r'每\s*天'), "每天"),
    (re.compile(r'每\s*周'), "每周"),
    (re.compile(r'每\s*个\s*周末'), "每逢周末"),
    (re.compile(r'每\s*月'), "每月"),
    (re.compile(r'每\s*年'), "每年"),
    (re.compile(r'经常\s*在\s*\w+\s*天'), None),  # 特殊处理
]

# 日期格式
_RE_DATE = re.compile(r'(\d{4})\s*[-年/]\s*(\d{1,2})\s*[-月/]\s*(\d{1,2})')
_RE_WEEKDAY = re.compile(r'(?:这|上|下|本)\s*周(?P<dir>[一二三四五六日])')
_RE_MONTH_DAY = re.compile(r'(\d{1,2})\s*月\s*(\d{1,2})\s*(?:号|日)')


def _parse_relative_date(text: str, now: datetime) -> Optional[datetime]:
    """Extract a concrete date from relative expressions like '昨天'."""
    for keyword, offset in _RELATIVE_MAP.items():
        if keyword in text:
            return now + timedelta(days=offset)
    return None


def _parse_date_literal(text: str) -> Optional[str]:
    """Return YYYY-MM-DD if a date literal is found, else None."""
    m = _RE_DATE.search(text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = _RE_MONTH_DAY.search(text)
    if m:
        today = datetime.now()
        return f"{today.year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


def _parse_recurring(text: str) -> List[str]:
    """Extract recurring-time keywords."""
    result = []
    for pat, label in _RECURRING_PATTERNS:
        if pat.search(text):
            if label:
                result.append(label)
            else:
                # e.g. "经常在星期天" -> extract weekday
                wd = re.search(r'星期[一二三四五六日]', text)
                if wd:
                    result.append(wd.group(0))
    return result


def extract_time_references(text: str) -> List[Tuple[str, Optional[str]]]:
    """Extract time references from a text string.

    Returns list of (time_reference, iso_date_or_None).
    Always includes at least the creation date as a fallback.
    """
    refs: List[Tuple[str, Optional[str]]] = []
    now = datetime.now()

    # 1) Date literals
    date_str = _parse_date_literal(text)
    if date_str:
        refs.append((date_str, date_str))

    # 2) Relative dates
    rel_date = _parse_relative_date(text, now)
    if rel_date:
        rel_label = (text[:30] if len(text) > 30 else text)
        # Find the specific keyword
        for kw in _RELATIVE_MAP:
            if kw in text:
                refs.append((kw, rel_date.strftime("%Y-%m-%d")))
                break

    # 3) Recurring patterns
    for label in _parse_recurring(text):
        refs.append((label, None))

    # 4) Time-of-day hints
    time_patterns = [
        (re.compile(r'早上'), "上午"),
        (re.compile(r'中午'), "中午"),
        (re.compile(r'下午'), "下午"),
        (re.compile(r'晚上|晚间'), "晚上"),
        (re.compile(r'昨天[上下]?午'), "昨天下午"),
        (re.compile(r'今天早上'), "今天早上"),
    ]
    for pat, label in time_patterns:
        if pat.search(text):
            refs.append((label, None))

    # Fallback: always include creation date
    if not refs:
        refs.append(("当天", now.strftime("%Y-%m-%d")))

    return refs


def classify_time_anchor(text: str) -> str:
    """Return a short human-readable anchor for display in timeline views."""
    if _parse_date_literal(text):
        return _parse_date_literal(text)
    for kw in ("昨天", "前天", "今天", "明天", "后天"):
        if kw in text:
            return kw
    for pat, label in _RECURRING_PATTERNS:
        if pat.search(text):
            return label
    return "当天"
