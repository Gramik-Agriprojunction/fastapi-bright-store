"""Keep product, store, metric, and date across follow-up questions."""

from __future__ import annotations

from app.modules.webtechAIAgent.reconciliation.intent_mapping import PERIOD_REPORTS, SNAPSHOT_REPORTS
from app.modules.webtechAIAgent.reconciliation.intent_registry import (
    PERIOD_INTENTS,
    SNAPSHOT_INTENTS,
)

PERIOD = PERIOD_INTENTS | PERIOD_REPORTS
SNAPSHOT = SNAPSHOT_INTENTS | SNAPSHOT_REPORTS

EMPTY: dict[str, object] = {
    "intent": None,
    "stores": [],
    "unknown_stores": [],
    "product_matched": False,
    "unknown_products": [],
    "date_filter": None,
    "mode": "total",
    "group_by": None,
}


def merge(previous: dict[str, object] | None, parsed: dict[str, object]) -> dict[str, object]:
    context = dict(EMPTY)
    if previous:
        context.update(previous)
        context["stores"] = list(previous.get("stores") or [])
        context["unknown_stores"] = list(previous.get("unknown_stores") or [])
        context["unknown_products"] = list(previous.get("unknown_products") or [])

    if parsed["intent_explicit"]:
        context["intent"] = parsed["intent"]
        previous_intent = str((previous or {}).get("intent") or "")
        new_intent = str(parsed["intent"] or "")
        if not parsed["date_explicit"]:
            if new_intent in SNAPSHOT and previous_intent in PERIOD:
                context["date_filter"] = {"type": "current"}
            elif new_intent in PERIOD and previous_intent in SNAPSHOT:
                context["date_filter"] = {"type": "all"}
    if parsed["stores_explicit"]:
        context["stores"] = list(parsed["stores"])
        context["unknown_stores"] = list(parsed["unknown_stores"])
    if parsed["product_explicit"]:
        context["product_matched"] = parsed["product_matched"]
        context["unknown_products"] = list(parsed["unknown_products"])
    if parsed["date_explicit"]:
        context["date_filter"] = parsed["date_filter"]
    if parsed["mode_explicit"]:
        context["mode"] = parsed["mode"]
    if parsed["group_by"]:
        context["group_by"] = parsed["group_by"]
    if parsed.get("columns_explicit"):
        context["columns"] = list(parsed.get("columns") or [])
    elif parsed.get("intent_explicit"):
        context["columns"] = []
    context["delivery"] = parsed.get("delivery")
    context["display_mode"] = parsed.get("display_mode") or "chat"
    previous_page = int(context.get("page") or 1)
    turn = parsed.get("page_turn")
    if parsed.get("intent_explicit") or parsed.get("date_explicit"):
        context["page"] = 1
    elif turn == "next":
        context["page"] = previous_page + 1
    elif turn == "prev":
        context["page"] = max(1, previous_page - 1)
    else:
        context["page"] = 1

    intent = context.get("intent")
    date_filter = context.get("date_filter")
    if intent in SNAPSHOT and isinstance(date_filter, dict) and date_filter.get("type") == "all":
        context["date_filter"] = {"type": "current"}
    if intent in PERIOD and context.get("date_filter") is None:
        context["date_filter"] = {"type": "all"}
    if intent in SNAPSHOT and context.get("date_filter") is None:
        context["date_filter"] = {"type": "current"}
    if not context.get("mode"):
        context["mode"] = "total"
    return context
