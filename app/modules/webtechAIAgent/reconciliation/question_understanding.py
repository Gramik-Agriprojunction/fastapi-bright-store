"""Turn a Hindi, Hinglish, or English question into a structured query."""

from __future__ import annotations

import re
from datetime import date, timedelta

from app.modules.webtechAIAgent.reconciliation.column_selection import select_columns
from app.modules.webtechAIAgent.reconciliation.entity_normalization import norm, search_terms
from app.modules.webtechAIAgent.reconciliation.intent_mapping import (
    REPORT_INTENTS,
    data_intent,
    detect_delivery,
    detect_page_turn,
    display_mode,
    soften,
)
from app.modules.webtechAIAgent.reconciliation.intent_registry import INTENTS

MONTHS = {
    "january": 1, "janvari": 1, "jan": 1,
    "february": 2, "farvari": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sitambar": 9, "sitamber": 9, "sept": 9, "sep": 9,
    "october": 10, "aktubar": 10, "oct": 10,
    "november": 11, "navambar": 11, "nov": 11,
    "december": 12, "disambar": 12, "dec": 12,
}

SIGNAL = re.compile(
    r"stock|sale|qty|kitna|kitni|kitne|on hand|rto|transit|musturd|mustard|muster|lavkush|"
    r"barabanki|gramino|fatehpur|lmd|reconcil|deliver|outgoing|hona chahiye|"
    r"1445|1666|reserved|cancel|inward|bikri|wapas|mismatch|variance|expected|"
    r"available|free|report|summary|hisab|sara kuch|sare kuch|sab kuch|"
    r"dc|challan|number wise|numberwise|\bback\b|\bin\b|"
    r"ledger|sale out|rto in|outgoing|excel|xlsx|workbook|jane wala|delivered order"
)


def detect_intent(text: str) -> str | None:
    plain = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", " ", text or "")
    hay = soften(plain)
    if "expected" in hay and any(word in hay for word in ("mismatch", "gap", "variance", "difference")):
        return "stock_variance"
    if "on hand" in hay and "expected" in hay:
        return "stock_variance"
    if any(phrase in hay for phrase in ("sara kuch", "sare kuch", "sab kuch", "sab de do", "poora de do", "pura de do", "everything")):
        return "everything"
    if re.search(r"\bdc\b", hay):
        return "delivered_dc"
    if re.search(r"\bback\b", hay):
        return "back_received"
    mapped = data_intent(plain)
    if mapped:
        return mapped
    if detect_delivery(text):
        return None
    if re.search(r"\bin\b", hay) and "transit" not in hay:
        return "stock_inward"
    for item in INTENTS:
        phrases = item["phrases"]
        if isinstance(phrases, list) and any(phrase in hay for phrase in phrases):
            code = str(item["code"])
            if code == "stock_variance" and "dono store" in hay:
                return "store_comparison"
            return code
    return None


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return date(year, month, 1), last


def _named_month(hay: str, today: date) -> tuple[date, date] | None:
    year_match = re.search(r"\b(20\d{2})\b", hay)
    year = int(year_match.group(1)) if year_match else today.year
    month_name = next(
        (name for name in sorted(MONTHS, key=len, reverse=True) if re.search(rf"\b{name}\b", hay)),
        None,
    )
    if not month_name:
        return None
    return _month_bounds(year, MONTHS[month_name])


def detect_date(text: str, today: date) -> dict[str, str] | None:
    hay = norm(text)
    if re.search(r"\b(aaj|today|is din)\b", hay):
        return {"type": "today", "start": today.isoformat(), "end": today.isoformat()}
    if re.search(r"\b(kal|yesterday|pichla din|pichle din)\b", hay):
        day = today - timedelta(days=1)
        return {"type": "yesterday", "start": day.isoformat(), "end": day.isoformat()}
    if re.search(r"\b(this month|is mahine|is month|current month)\b", hay):
        start, end = _month_bounds(today.year, today.month)
        return {"type": "month", "start": start.isoformat(), "end": end.isoformat()}
    if re.search(r"\b(last month|pichla mahine|pichle mahine|previous month)\b", hay):
        month = 12 if today.month == 1 else today.month - 1
        year = today.year - 1 if today.month == 1 else today.year
        start, end = _month_bounds(year, month)
        return {"type": "month", "start": start.isoformat(), "end": end.isoformat()}
    iso_hits = re.findall(r"\b(20\d{2})-(\d{2})-(\d{2})\b", hay)
    dmy_hits = re.findall(r"\b([0-3]?\d)[/-]([01]?\d)[/-](20\d{2})\b", hay)
    named = list(re.finditer(
        r"\b([0-3]?\d)\s+(january|jan|february|feb|march|mar|april|apr|may|june|jun|"
        r"july|jul|august|aug|september|sep|sept|october|oct|november|nov|december|dec)"
        r"(?:\s+(20\d{2}))?\b",
        hay,
    ))
    points: list[date] = []
    for year, month, day in iso_hits:
        points.append(date(int(year), int(month), int(day)))
    for day, month, year in dmy_hits:
        points.append(date(int(year), int(month), int(day)))
    for match in named:
        year = int(match.group(3) or today.year)
        points.append(date(year, MONTHS[match.group(2)], int(match.group(1))))
    if len(points) >= 2 and re.search(r"\b(se|to|tak)\b", hay):
        start, end = sorted(points[:2])
        return {"type": "range", "start": start.isoformat(), "end": end.isoformat()}
    if len(points) == 1:
        day = points[0]
        return {"type": "day", "start": day.isoformat(), "end": day.isoformat()}
    bounds = _named_month(hay, today)
    if bounds:
        return {"type": "month", "start": bounds[0].isoformat(), "end": bounds[1].isoformat()}
    if re.search(r"\b(poora|pura|pure|total|sab|all|hisaab|hisab|ab tak|abhi tak)\b", hay):
        return {"type": "all"}
    return None


def detect_mode(text: str) -> str | None:
    if re.search(r"\b(list|detail|documents|dikhao|kaun se|konsi)\b", norm(text)):
        return "list"
    if re.search(r"\b(total|kitna|kitni|qty|quantity)\b", norm(text)):
        return "total"
    return None


def understand(text: str, today: date) -> dict[str, object]:
    intent = detect_intent(text)
    date_filter = detect_date(text, today)
    if intent == "date_range_sales" and date_filter and date_filter.get("type") == "today":
        intent = "today_sales"
    if intent == "lmd_picked_qty" and date_filter and date_filter.get("type") == "today":
        intent = "today_lmd_picked"
    mode = detect_mode(text)
    hay = soften(text)
    if intent in REPORT_INTENTS or intent in {"delivered_dc", "back_received"} or (
        intent == "stock_inward" and re.search(r"\bin\b", hay)
    ):
        mode = "list"
    columns, columns_explicit = select_columns(text, intent) if intent in REPORT_INTENTS else ([], False)
    if not columns_explicit:
        columns = []
    return {
        "intent": intent,
        "intent_explicit": intent is not None,
        "delivery": detect_delivery(text),
        "display_mode": display_mode(text),
        "page_turn": detect_page_turn(text),
        "columns": columns,
        "columns_explicit": columns_explicit,
        "terms": search_terms(text),
        "stores": [],
        "unknown_stores": [],
        "stores_explicit": False,
        "product_matched": False,
        "unknown_products": [],
        "product_explicit": False,
        "date_filter": date_filter,
        "date_explicit": date_filter is not None,
        "mode": mode,
        "mode_explicit": mode is not None or intent in {"delivered_dc", "back_received"},
        "group_by": "store" if "store wise" in hay or "storewise" in hay else None,
        "handled_signal": bool(
            SIGNAL.search(norm(text))
            or SIGNAL.search(hay)
            or date_filter
            or intent
            or detect_delivery(text)
            or detect_page_turn(text)
        ),
    }
