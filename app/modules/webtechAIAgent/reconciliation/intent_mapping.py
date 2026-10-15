"""Canonical inventory intents. Phrase order is specific before general."""

from __future__ import annotations

import re

from app.modules.webtechAIAgent.reconciliation.entity_normalization import norm

PERIOD_REPORTS = {
    "SALES_LEDGER",
    "SALES_OUT_REPORT",
    "DELIVERED_ORDERS",
    "RTO_RECEIVED_REPORT",
    "INCOMING_STOCK_REPORT",
    "OUTGOING_STOCK_REPORT",
    "IN_TRANSIT_REPORT",
    "CANCELLED_ORDERS_REPORT",
}

SNAPSHOT_REPORTS = {
    "LIVE_STOCK_REPORT",
    "STOCK_RECONCILIATION",
    "PRODUCT_STOCK_SUMMARY",
}

DELIVERY_INTENTS = {"GENERATE_EXCEL_REPORT", "EMAIL_REPORT"}

REPORT_INTENTS = PERIOD_REPORTS | SNAPSHOT_REPORTS

ALL_SHEETS = (
    "Summary",
    "Sales Ledger",
    "Delivered Orders",
    "RTO Received",
    "Incoming Stock",
    "Outgoing Stock",
    "In Transit",
    "Cancelled Orders",
    "Live Stock",
)

INTENT_SHEETS: dict[str, tuple[str, ...]] = {
    "SALES_LEDGER": ("Summary", "Sales Ledger"),
    "SALES_OUT_REPORT": ("Summary", "Sales Ledger"),
    "DELIVERED_ORDERS": ("Delivered Orders",),
    "RTO_RECEIVED_REPORT": ("RTO Received",),
    "INCOMING_STOCK_REPORT": ("Incoming Stock",),
    "OUTGOING_STOCK_REPORT": ("Outgoing Stock",),
    "IN_TRANSIT_REPORT": ("In Transit",),
    "CANCELLED_ORDERS_REPORT": ("Cancelled Orders",),
    "LIVE_STOCK_REPORT": ("Live Stock",),
    "STOCK_RECONCILIATION": ("Summary", "Live Stock"),
    "PRODUCT_STOCK_SUMMARY": ("Summary", "Live Stock"),
    "GENERATE_EXCEL_REPORT": ALL_SHEETS,
}

COMPLETE_SHEETS = ALL_SHEETS

_TYPOS = {
    "ledgar": "ledger",
    "leger": "ledger",
    "recieve": "receive",
    "recieved": "received",
    "delivred": "delivered",
    "deliverd": "delivered",
    "outgoin": "outgoing",
    "prodct": "product",
    "qunatity": "quantity",
    "quantty": "quantity",
}


def soften(text: str) -> str:
    words = [_TYPOS.get(word, word) for word in norm(text).split()]
    return " ".join(words)


def data_intent(text: str) -> str | None:
    """Map a question to a report intent. None leaves the legacy matcher in charge."""
    hay = soften(text)
    if "rto in transit" in hay or "return in transit" in hay:
        return None
    if ("sale out" in hay and "rto in" in hay) or "ledger" in hay:
        return "SALES_LEDGER"
    if "rto in" in hay and "transit" not in hay:
        return "RTO_RECEIVED_REPORT"
    if ("product wise" in hay or "productwise" in hay) and any(
        word in hay for word in ("sale", "sales", "detail", "details")
    ):
        return "SALES_OUT_REPORT"
    if "sale out" in hay:
        return "SALES_OUT_REPORT"
    if "delivered order" in hay:
        return "DELIVERED_ORDERS"
    received = (
        "receive", "received", "receipt", "ho chuk", "aa chuk", "aa gaya", "aaya", "mil gaya", "mil chuk",
    )
    if "rto" in hay and "transit" not in hay and any(phrase in hay for phrase in received):
        return "RTO_RECEIVED_REPORT"
    if any(phrase in hay for phrase in ("incoming stock", "incoming", "inward", "stock aaya")):
        return "INCOMING_STOCK_REPORT"
    if any(phrase in hay for phrase in ("outgoing", "jane wala", "jaane wala", "ja raha", "bahar ja")):
        return "OUTGOING_STOCK_REPORT"
    if "in transit" in hay or re.search(r"\btransit\b", hay):
        return "IN_TRANSIT_REPORT"
    if "cancel" in hay:
        return "CANCELLED_ORDERS_REPORT"
    if "live stock" in hay:
        return "LIVE_STOCK_REPORT"
    if any(phrase in hay for phrase in ("reconcil", "mismatch", "variance")) and "stock summary" not in hay:
        return "STOCK_RECONCILIATION"
    stock_bits = ("on hand", "reserved", "free qty", "free stock", "expected", "variance")
    if "stock summary" in hay or "product stock" in hay or sum(bit in hay for bit in stock_bits) >= 2:
        return "PRODUCT_STOCK_SUMMARY"
    return None


def display_mode(text: str) -> str:
    """Chat unless the user explicitly asks for an Excel file."""
    hay = soften(text)
    if re.search(r"\b(excel|xlsx|xls)\b", hay) or "workbook" in hay:
        return "excel"
    download = "download" in hay or "export" in hay
    if download and any(word in hay for word in ("report", "file", "excel", "xlsx", "xls")):
        return "excel"
    if "report bana" in hay and "download" in hay:
        return "excel"
    return "chat"


def detect_delivery(text: str) -> str | None:
    hay = soften(text)
    has_address = bool(re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or ""))
    mail_word = "mail" in hay or "email" in hay
    send_word = any(word in hay for word in ("bhej", "bhejo", "send", "mail", "email"))
    if has_address and send_word:
        return "EMAIL_REPORT"
    if mail_word and any(word in hay for word in ("bhej", "bhejo", "send", "report", "excel", "isko", "file", "kar", "karo")):
        return "EMAIL_REPORT"
    if display_mode(text) == "excel":
        return "GENERATE_EXCEL_REPORT"
    return None


def sheets_for(intent: str, complete: bool) -> tuple[str, ...]:
    if complete or intent in {"GENERATE_EXCEL_REPORT", "everything"}:
        return COMPLETE_SHEETS
    return INTENT_SHEETS.get(intent, ("Summary",))


def detect_page_turn(text: str) -> str | None:
    hay = soften(text)
    if any(phrase in hay for phrase in ("aur dikhao", "aur dikha", "next page", "agla page")):
        return "next"
    if any(phrase in hay for phrase in ("previous page", "pichla page", "pichhla page")):
        return "prev"
    return None


def wants_previous_file(text: str) -> bool:
    hay = soften(text)
    return any(phrase in hay for phrase in ("same format", "previous report", "jaise", "pichli report", "pehli report"))
