"""Ask Odoo a reconciliation question. Any warehouse, any product, same buckets."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.modules.webtechAIAgent.reconciliation.answer_formatting import (
    document_lines,
    lines,
    product_line,
    snapshot_line,
    stock_card,
    store_line,
)
from app.modules.webtechAIAgent.reconciliation.conversation_context import merge
from app.modules.webtechAIAgent.reconciliation.dictionary import UNSUPPORTED
from app.modules.webtechAIAgent.reconciliation.entity_normalization import norm
from app.modules.webtechAIAgent.reconciliation.excel_export import (
    export_store_by_id,
    wants_store_excel,
)
from app.modules.webtechAIAgent.reconciliation.excel_mail import (
    email_addresses,
    send_excel_files,
    wants_excel_mail,
    without_emails,
)
from app.modules.webtechAIAgent.reconciliation.intent_mapping import wants_previous_file
from app.modules.webtechAIAgent.reconciliation.inventory_query import (
    cumulative,
    document_row,
    expected_until,
    movements,
    open_rto,
    outside_snapshot,
    period_bounds,
    qty,
    running_until,
)
from app.modules.webtechAIAgent.reconciliation.odoo_ledger import build_book, resolve
from app.modules.webtechAIAgent.reconciliation.query_execution import REPORT_INTENTS, execute_report
from app.modules.webtechAIAgent.reconciliation.question_understanding import understand
from app.modules.webtechAIAgent.reconciliation.report_generation import save_report, validate_for_email
from app.modules.webtechAIAgent.reconciliation.workbook import Book, Move

IST = ZoneInfo("Asia/Kolkata")
CODE_WORDS = {
    "rename", "title", "login", "screen", "button", "css", "component",
    "function", "commit", "branch", "refactor", "bug", "fix",
}
SALES_INTENTS = {"date_range_sales", "today_sales", "stock_outward"}
STOCK_INTENTS = {"on_hand_qty", "current_stock", "physical_stock", "store_wise_stock"}
INWARD_INTENTS = {"stock_inward", "incoming_transfer"}


def ist_today() -> date:
    return datetime.now(IST).date()


def _end_day(bounds: tuple[date, date] | str, book: Book) -> date:
    if isinstance(bounds, str):
        return book.snapshot
    return bounds[1]


def _unknown_note(context: dict[str, object]) -> str:
    notes = []
    products = list(context.get("unknown_products") or [])
    stores = list(context.get("unknown_stores") or [])
    if products and context.get("product_matched"):
        notes.append(f"{', '.join(products)} is file mein nahi hai, isliye uska qty nahi diya.")
    if stores and context.get("stores"):
        notes.append(f"{', '.join(stores)} match nahi hua, isliye uska qty nahi diya.")
    return "\n".join(notes)


def _movement_answer(
    book: Book,
    rows: list[Move],
    title: str,
    field: str,
    formula: str,
    note: str,
    mode: str,
    bounds: tuple[date, date],
) -> dict[str, object]:
    amount_rows = []
    for row in rows:
        value = getattr(row, field)
        if value is None and field != "demand":
            continue
        amount_rows.append(row)
    total = 0.0
    counted = 0
    payload = []
    for row in amount_rows:
        value = getattr(row, field)
        if value is None:
            continue
        total += value
        counted += 1
        payload.append(document_row(row, value))
    period = f"{bounds[0].isoformat()} se {bounds[1].isoformat()}"
    body = lines(
        f"{product_line(book)} — {title}",
        store_line(book),
        f"Period {period}",
        f"Total {qty(total)} qty · {counted} documents",
        formula,
        note,
        document_lines(payload) if mode == "list" else "",
    )
    return {"reply": body, "rows": payload if mode == "list" else []}


def _stock_answer(book: Book, context: dict[str, object], today: date) -> dict[str, object]:
    date_filter = context.get("date_filter")
    if not isinstance(date_filter, dict):
        date_filter = {"type": "current"}
    blocked = outside_snapshot(book, today, date_filter)
    kind = date_filter.get("type")
    if kind in {"current", None} or (kind == "today" and blocked):
        return {
            "reply": stock_card(
                location=book.warehouse or book.store_name,
                product_name=book.product_name,
                sku=book.sku,
                variant=book.variant,
                updated_at=book.stock_updated_at,
                snapshot=book.snapshot,
                on_hand=book.live_on_hand,
                reserved=book.live_reserved,
                incoming=book.incoming_qty,
            ),
            "rows": [],
        }

    bounds = period_bounds(book, date_filter, today)
    if isinstance(bounds, str):
        return {"reply": bounds, "rows": []}
    last = running_until(book, bounds[1])
    if last is None:
        return {
            "reply": (
                f"{bounds[1].isoformat()} tak ledger mein running on hand nahi hai. "
                f"Pehli stock entry {book.first_day} ko IN hai."
            ),
            "rows": [],
        }
    reply = lines(
        f"{product_line(book)} — Running on hand",
        store_line(book),
        f"{bounds[1].isoformat()} ke last stock-changing movement ke baad {qty(last.running)} qty",
        f"Document {last.doc} · {last.bucket}",
            "Yeh us din ke movements se chala hua on-hand hai. Live on-hand alag se current stock hai.",
        _unknown_note(context),
    )
    return {"reply": reply, "rows": []}


def _expected_answer(book: Book, context: dict[str, object], today: date) -> dict[str, object]:
    date_filter = context.get("date_filter") if isinstance(context.get("date_filter"), dict) else {"type": "current"}
    blocked = outside_snapshot(book, today, date_filter)
    if blocked and date_filter.get("type") in {"today", "yesterday"}:
        return {"reply": blocked, "rows": []}
    end = book.snapshot if date_filter.get("type") in {"current", "all", None} else _end_day(
        period_bounds(book, date_filter, today), book
    )
    if isinstance(period_bounds(book, date_filter, today), str) and date_filter.get("type") not in {"current", "all", None}:
        return {"reply": str(period_bounds(book, date_filter, today)), "rows": []}
    inward = sum(row.qty_in or 0 for row in cumulative(book, "IN", end))
    sold = sum(row.qty_out or 0 for row in cumulative(book, "Delivered", end))
    returned = sum(row.qty_in or 0 for row in cumulative(book, "RTO", end))
    should = expected_until(book, end)
    rule = book.rules.get("Hona chahiye (on hand)")
    reply = lines(
        f"{product_line(book)} — Hona chahiye",
        store_line(book),
        f"Through {end.isoformat()}",
        f"IN {qty(inward)} − Delivered {qty(sold)} + RTO {qty(returned)} = {qty(should)}",
        rule.formula if rule else "Formula: IN − successful delivered + RTO received.",
        "Outgoing is formula mein nahi kata. Woh abhi on hand ke andar reserved hai.",
        "Adjustment IN judta hai, Adjustment OUT kat ta hai, jab stock mein ho.",
        "Transit leg ko IN mein dobara nahi joda.",
        _unknown_note(context),
    )
    return {"reply": reply, "rows": []}


def _variance_answer(book: Book, context: dict[str, object], today: date) -> dict[str, object]:
    if book.live_on_hand is None:
        return {"reply": "Live Stock sheet mein on-hand cell khali hai.", "rows": []}
    should = expected_until(book, book.snapshot)
    gap = book.live_on_hand - should
    status = "matched" if abs(gap) < 0.001 else "mismatch"
    rule = book.rules.get("Gap")
    reply = lines(
        f"{product_line(book)} — Reconciliation",
        store_line(book),
        snapshot_line(book),
        f"Hona chahiye {qty(should)}",
        f"Live on hand {qty(book.live_on_hand)}",
        f"Gap {qty(gap)} · {status}",
        rule.how if rule else "Gap = live on hand minus hona chahiye.",
        _unknown_note(context),
    )
    return {"reply": reply, "rows": []}


def _period_metric(
    book: Book,
    context: dict[str, object],
    today: date,
    bucket: str,
    field: str,
    title: str,
    formula: str,
    note: str,
) -> dict[str, object]:
    date_filter = context.get("date_filter") if isinstance(context.get("date_filter"), dict) else {"type": "all"}
    blocked = outside_snapshot(book, today, date_filter)
    if blocked:
        return {"reply": blocked, "rows": []}
    bounds = period_bounds(book, date_filter, today)
    if isinstance(bounds, str):
        return {"reply": bounds, "rows": []}
    rows = movements(book, bucket, bounds[0], bounds[1])
    result = _movement_answer(
        book, rows, title, field, formula, note, str(context.get("mode") or "total"), bounds
    )
    note_extra = _unknown_note(context)
    if note_extra:
        result["reply"] = f"{result['reply']}\n{note_extra}"
    return result


def _result_card(
    book: Book,
    rows: list[Move],
    title: str,
    qty_label: str,
    field: str,
    page: int,
) -> dict[str, object]:
    """Same one-column qty card the Sale out report renders in chat."""
    page_size = 20
    page = max(1, int(page or 1))
    start = (page - 1) * page_size
    shown = rows[start:start + page_size]
    table_rows = [
        {qty_label: qty(getattr(row, field) if isinstance(getattr(row, field), (int, float)) else None)}
        for row in shown
    ]
    total = sum(getattr(row, field) or 0 for row in rows)
    return {
        "title": title,
        "columns": [qty_label],
        "rows": table_rows,
        "record_count": len(rows),
        "page": page,
        "page_size": page_size,
        "from": (start + 1) if table_rows else 0,
        "to": start + len(table_rows),
        "totals": {qty_label: qty(total)},
    }


def _numbered(rows: list, field: str) -> list[str]:
    return [
        f"{index}. {row.doc} · {qty(getattr(row, field))}"
        for index, row in enumerate(rows, start=1)
    ]


def _everything_answer(book: Book, context: dict[str, object], today: date) -> dict[str, object]:
    """Same buckets as the reconciliation Excel, each In, DC, and Back document on its own line."""
    date_filter = context.get("date_filter") if isinstance(context.get("date_filter"), dict) else {"type": "all"}
    bounds = period_bounds(book, date_filter, today)
    if isinstance(bounds, str):
        return {"reply": bounds, "rows": []}
    start, end = bounds
    inward = movements(book, "IN", start, end)
    sold = movements(book, "Delivered", start, end)
    returned = movements(book, "RTO", start, end)
    in_qty = sum(row.qty_in or 0 for row in inward)
    sale_qty = sum(row.qty_out or 0 for row in sold)
    rto_qty = sum(row.qty_in or 0 for row in returned)
    reply = lines(
        f"{product_line(book)} — Sara kuch",
        store_line(book),
        f"{start.isoformat()} se {end.isoformat()}",
        f"On hand {qty(book.live_on_hand)}",
        f"Sale out {qty(sale_qty)}",
        f"RTO {qty(rto_qty)}",
        f"In {qty(in_qty)}",
        *_numbered(inward, "qty_in"),
        f"DC In {qty(sale_qty)}",
        f"DC count {len(sold)}",
        *_numbered(sold, "qty_out"),
        f"Back {qty(rto_qty)}",
        *_numbered(returned, "qty_in"),
    )
    return {"reply": reply, "rows": []}


def _delivered_dc_answer(book: Book, context: dict[str, object], today: date) -> dict[str, object]:
    """Delivered challans: document count, product qty sum, and qty against each DC number."""
    date_filter = context.get("date_filter") if isinstance(context.get("date_filter"), dict) else {"type": "all"}
    blocked = outside_snapshot(book, today, date_filter)
    if blocked:
        return {"reply": blocked, "rows": []}
    bounds = period_bounds(book, date_filter, today)
    if isinstance(bounds, str):
        return {"reply": bounds, "rows": []}
    rows = movements(book, "Delivered", bounds[0], bounds[1])
    total = sum(row.qty_out or 0 for row in rows)
    numbered = [
        f"{index}. {row.doc} · {qty(row.qty_out)}"
        for index, row in enumerate(rows, start=1)
    ]
    reply = lines(
        f"{product_line(book)} — DC In",
        store_line(book),
        f"Period {bounds[0].isoformat()} se {bounds[1].isoformat()}",
        f"{bounds[0].isoformat()} se {bounds[1].isoformat()}",
        f"DC count {len(rows)}",
        f"Product wise sum {qty(total)} qty",
        "\n".join(numbered),
    )
    return {
        "reply": reply,
        "rows": [document_row(row, row.qty_out) for row in rows],
        "table": _result_card(book, rows, "DC In", "DC In", "qty_out", int(context.get("page") or 1)),
    }


def _back_answer(book: Book, context: dict[str, object], today: date) -> dict[str, object]:
    """RTO rows from the same Excel bucket: stock that came back, one document at a time."""
    date_filter = context.get("date_filter") if isinstance(context.get("date_filter"), dict) else {"type": "all"}
    bounds = period_bounds(book, date_filter, today)
    if isinstance(bounds, str):
        return {"reply": bounds, "rows": []}
    rows = movements(book, "RTO", bounds[0], bounds[1])
    total = sum(row.qty_in or 0 for row in rows)
    reply = lines(
        f"{product_line(book)} — Back",
        store_line(book),
        f"Period {bounds[0].isoformat()} se {bounds[1].isoformat()}",
        f"{bounds[0].isoformat()} se {bounds[1].isoformat()}",
        f"Back {qty(total)}",
        f"Back count {len(rows)}",
        *_numbered(rows, "qty_in"),
    )
    return {
        "reply": reply,
        "rows": [document_row(row, row.qty_in) for row in rows],
        "table": _result_card(book, rows, "Back", "Back", "qty_in", int(context.get("page") or 1)),
    }


def answer_question(book: Book, context: dict[str, object], today: date) -> dict[str, object]:
    intent = str(context.get("intent") or "")
    if intent in REPORT_INTENTS:
        return execute_report(book, context, today)
    if intent in UNSUPPORTED or intent == "today_lmd_picked":
        return {"reply": UNSUPPORTED.get(intent) or UNSUPPORTED["lmd_picked_qty"], "rows": []}
    if intent == "everything":
        return _everything_answer(book, context, today)
    if intent == "delivered_dc":
        return _delivered_dc_answer(book, context, today)
    if intent == "back_received":
        return _back_answer(book, context, today)
    if not intent:
        return {
            "reply": "Kya chahiye: on hand, sale out, RTO, In, DC In, ya back?",
            "rows": [],
        }
    if intent in STOCK_INTENTS:
        return _stock_answer(book, context, today)
    if intent == "expected_stock":
        return _expected_answer(book, context, today)
    if intent in {"stock_variance", "reconciliation_difference", "reconciliation_status"}:
        return _variance_answer(book, context, today)
    if intent in SALES_INTENTS:
        return _period_metric(
            book, context, today, "Delivered", "qty_out", "Delivered sale",
            "Delivered bucket, done qty",
            "Yeh customer delivery hai. LMD picking nahi hai, aur outgoing (assigned) shamil nahi hai.",
        )
    if intent in INWARD_INTENTS:
        return _period_metric(
            book, context, today, "IN", "qty_in", "IN received",
            "IN bucket, qty into the warehouse stock location",
            "Transit leg alag hai. Woh store stock tab banta hai jab IN document done ho.",
        )
    if intent == "rto_received":
        result = _period_metric(
            book, context, today, "RTO", "qty_in", "RTO",
            "RTO bucket, qty received back",
            "RTO wapas store mein aaya hua qty hai. Sale se alag hai.",
        )
        date_filter = context.get("date_filter") if isinstance(context.get("date_filter"), dict) else {"type": "all"}
        bounds = period_bounds(book, date_filter, today)
        if isinstance(bounds, tuple):
            card_rows = movements(book, "RTO", bounds[0], bounds[1])
            result["table"] = _result_card(
                book, card_rows, "RTO", "RTO", "qty_in", int(context.get("page") or 1)
            )
        return result
    if intent == "outgoing_transfer":
        return _period_metric(
            book, context, today, "Outgoing", "qty_out", "Outgoing assigned",
            "Outgoing bucket, assigned qty still in on hand",
            "Yeh store-to-store transfer nahi hai. Assigned customer delivery hai, on hand mein abhi pada hai.",
        )
    if intent == "cancelled_qty":
        return _period_metric(
            book, context, today, "Cancelled", "demand", "Cancelled demand",
            "Cancelled demand ordered qty hai. Done qty 0 hai.",
            "Cancel hone se stock nahi ghata. Demand ordered qty hai.",
        )
    if intent == "net_with_customers":
        date_filter = context.get("date_filter") if isinstance(context.get("date_filter"), dict) else {"type": "all"}
        bounds = period_bounds(book, date_filter, today)
        if isinstance(bounds, str):
            return {"reply": bounds, "rows": []}
        sold = sum(row.qty_out or 0 for row in movements(book, "Delivered", bounds[0], bounds[1]))
        returned = sum(row.qty_in or 0 for row in movements(book, "RTO", bounds[0], bounds[1]))
        reply = lines(
            f"{product_line(book)} — Customers ke paas",
            store_line(book),
            f"{bounds[0].isoformat()} se {bounds[1].isoformat()}",
            f"Delivered {qty(sold)} − RTO {qty(returned)} = {qty(sold - returned)}",
            "Formula: Summary B11 = B6 − B7, period par filter karke.",
        )
        return {"reply": reply, "rows": []}
    if intent == "free_qty":
        if book.live_on_hand is None or book.live_reserved is None:
            return {"reply": "Free qty ke liye Live Stock on-hand ya reserved cell khali hai.", "rows": []}
        free = book.live_on_hand - book.live_reserved
        reply = lines(
            f"{product_line(book)} — Free qty",
            store_line(book),
            snapshot_line(book),
            f"On hand {qty(book.live_on_hand)} − Reserved {qty(book.live_reserved)} = {qty(free)}",
            "Free ko available maana gaya hai. Yeh on-hand ke barabar nahi hai.",
        )
        return {"reply": reply, "rows": []}
    if intent == "reserved_qty":
        reply = lines(
            f"{product_line(book)} — Reserved",
            store_line(book),
            snapshot_line(book),
            f"Reserved {qty(book.live_reserved)}",
            "Outgoing assigned deliveries isi reserved qty ko hold karti hain.",
        )
        return {"reply": reply, "rows": []}
    if intent == "in_transit":
        reply = lines(
            f"{product_line(book)} — In transit",
            store_line(book),
            snapshot_line(book),
            f"Transit location abhi {qty(book.transit_on_hand)} qty",
            "Transit leg ko store IN mein dobara nahi joda jata.",
        )
        return {"reply": reply, "rows": []}
    if intent == "rto_in_transit":
        pending = open_rto(book)
        if not pending:
            reply = "RTO in transit: koi open return document nahi. Teeno RTO rows state done hain."
        else:
            reply = f"RTO in transit documents: {len(pending)}"
        return {"reply": reply, "rows": [document_row(row, row.qty_in) for row in pending]}
    if intent == "product_summary":
        should = expected_until(book, book.snapshot)
        sold = sum(row.qty_out or 0 for row in book.moves if row.bucket == "Delivered")
        returned = sum(row.qty_in or 0 for row in book.moves if row.bucket == "RTO")
        inward = sum(row.qty_in or 0 for row in book.moves if row.bucket == "IN")
        reply = lines(
            f"{product_line(book)} — Reconciliation summary",
            store_line(book),
            snapshot_line(book),
            f"IN {qty(inward)}",
            f"Delivered {qty(sold)}",
            f"RTO {qty(returned)}",
            f"Hona chahiye {qty(should)}",
            f"Live on hand {qty(book.live_on_hand)}",
            f"Reserved {qty(book.live_reserved)}",
            f"Free {qty((book.live_on_hand or 0) - (book.live_reserved or 0) if book.live_on_hand is not None and book.live_reserved is not None else None)}",
            f"Gap {qty((book.live_on_hand - should) if book.live_on_hand is not None else None)}",
            "LMD picking in buckets mein alag metric nahi hai.",
        )
        return {"reply": reply, "rows": []}
    if intent == "store_comparison":
        return {
            "reply": (
                f"{store_line(book)} · {product_line(book)}\n"
                f"Live on hand {qty(book.live_on_hand)} qty · {book.snapshot.isoformat()}"
            ),
            "rows": [],
        }
    return {
        "reply": f"{intent} in buckets se verify nahi ho saka.",
        "rows": [],
    }


def _public_context(context: dict[str, object]) -> dict[str, object]:
    return {
        "intent": context.get("intent"),
        "warehouses": context.get("warehouses") or [],
        "product": context.get("product"),
        "pending": context.get("pending"),
        "candidates": context.get("candidates") or [],
        "date_filter": context.get("date_filter"),
        "mode": context.get("mode") or "total",
        "group_by": context.get("group_by"),
        "excel_files": list(context.get("excel_files") or []),
        "columns": list(context.get("columns") or []),
        "delivery": context.get("delivery"),
        "display_mode": context.get("display_mode") or "chat",
        "page": int(context.get("page") or 1),
    }


def ask_reconciliation(
    message: str,
    incoming: dict[str, object] | None = None,
    today: date | None = None,
) -> dict[str, object]:
    result = _ask_reconciliation(message, incoming, today)
    return _attach_choices(result)


def _ask_reconciliation(
    message: str,
    incoming: dict[str, object] | None = None,
    today: date | None = None,
) -> dict[str, object]:
    text = str(message or "").strip()
    clock = today or ist_today()
    parsed = understand(text, clock)
    context = merge(incoming, parsed)
    terms = list(parsed.get("terms") or [])
    mail = wants_excel_mail(text)
    mentions_mail = any(word in norm(text) for word in ("mail", "email", "bhej", "bhejo", "send"))
    excel = wants_store_excel(text) or (
        str((incoming or {}).get("intent") or "") == "store_excel" and not mentions_mail
    )
    code_like = bool(set(terms) & CODE_WORDS) and not parsed["handled_signal"]
    follow_up = bool(
        (incoming or {}).get("intent")
        and not code_like
        and (
            parsed["date_explicit"]
            or parsed["mode_explicit"]
            or parsed["intent_explicit"]
            or (terms and len(terms) <= 3)
        )
    )
    choosing = bool((incoming or {}).get("pending") and (incoming or {}).get("candidates"))
    handled = bool(parsed["handled_signal"] or follow_up or excel or mail or mentions_mail or choosing)
    if not text:
        return {
            "handled": False,
            "reply": "Store, product, aur metric likho.",
            "context": context,
            "rows": [],
        }
    if not handled:
        return {"handled": False, "reply": "", "context": incoming or {}, "rows": []}
    if mentions_mail and not mail and not wants_store_excel(text) and not parsed.get("intent_explicit"):
        return {
            "handled": True,
            "reply": "Email address likho.",
            "context": _public_context(context),
            "rows": [],
        }
    if mail and not excel and not parsed.get("intent_explicit"):
        context["intent"] = context.get("intent") or "store_excel"
        paths = [str(item) for item in list(context.get("excel_files") or []) if item]
        sent = send_excel_files(email_addresses(text), paths)
        return {
            "handled": True,
            "reply": sent,
            "context": _public_context(context),
            "rows": [],
            "files": [{"name": Path(item).name, "path": item} for item in paths if Path(item).is_file()],
        }
    if (
        context.get("delivery") == "GENERATE_EXCEL_REPORT"
        and not parsed.get("intent_explicit")
        and wants_previous_file(text)
    ):
        paths = [str(item) for item in list(context.get("excel_files") or []) if item and Path(str(item)).is_file()]
        if paths:
            return {
                "handled": True,
                "reply": "Previous report ready.\n" + "\n".join(f"Excel: {item}" for item in paths),
                "context": _public_context(context),
                "rows": [],
                "files": [{"name": Path(item).name, "path": item} for item in paths],
            }
    if excel:
        context["intent"] = "store_excel"
        try:
            context, clarify = resolve(without_emails(text), context, require_product=False)
        except RuntimeError as exc:
            return {"handled": True, "reply": str(exc), "context": _public_context(context), "rows": []}
        if clarify:
            return {"handled": True, "reply": clarify, "context": _public_context(context), "rows": []}
        replies: list[str] = []
        paths: list[str] = []
        try:
            for warehouse in list(context.get("warehouses") or []):
                built = export_store_by_id(int(warehouse["id"]))
                if isinstance(built, str):
                    replies.append(built)
                    continue
                paths.append(str(built["path"]))
                replies.append(
                    "\n".join(
                        [
                            f"{warehouse.get('name')} — saare products ki reconciliation Excel",
                            f"File: {built['path']}",
                            f"Products {built['products']} · movements {built['moves']}",
                            f"Matched {built['matched']} · gap {built['gaps']}",
                            "Tabs: Summary, Ledger, IN, Delivered, RTO, In Transit, Outgoing, Cancelled, Live Stock.",
                            "Hona chahiye = IN + Adjustment IN + RTO − Delivered − Adjustment OUT + Other IN − Other OUT.",
                        ]
                    )
                )
        except RuntimeError as exc:
            return {"handled": True, "reply": str(exc), "context": _public_context(context), "rows": []}
        if paths:
            context["excel_files"] = paths
        if mail and paths:
            replies.append(send_excel_files(email_addresses(text), paths))
        return {
            "handled": True,
            "reply": "\n\n".join(replies) or "Warehouse aur Excel dono ke liye naam chahiye.",
            "context": _public_context(context),
            "rows": [],
            "files": [{"name": Path(item).name, "path": item} for item in paths],
            "source": {"system": "odoo", "as_of": clock.isoformat()},
        }
    if str(context.get("intent") or "") in UNSUPPORTED or context.get("intent") == "today_lmd_picked":
        return {
            "handled": True,
            "reply": UNSUPPORTED.get(str(context.get("intent"))) or UNSUPPORTED["lmd_picked_qty"],
            "context": _public_context(context),
            "rows": [],
        }
    try:
        context, clarify = resolve(text, context)
    except RuntimeError as exc:
        return {"handled": True, "reply": str(exc), "context": context, "rows": []}
    if clarify:
        return {"handled": True, "reply": clarify, "context": _public_context(context), "rows": []}
    product = context.get("product")
    warehouses = list(context.get("warehouses") or [])
    if not isinstance(product, dict) or not warehouses:
        return {
            "handled": True,
            "reply": "Warehouse aur product dono chahiye.",
            "context": _public_context(context),
            "rows": [],
        }
    context["message"] = text
    replies: list[str] = []
    rows: list[object] = []
    files: list[dict[str, str]] = []
    tables: list[dict[str, object]] = []
    built_books: list[Book] = []
    try:
        for warehouse in warehouses:
            built = build_book(int(warehouse["id"]), product, clock)
            if isinstance(built, str):
                replies.append(built)
                continue
            built_books.append(built)
            result = answer_question(built, context, clock)
            replies.append(str(result["reply"]))
            rows.extend(result["rows"])
            chat = result.get("table")
            if isinstance(chat, dict):
                tables.append(chat)
    except RuntimeError as exc:
        return {"handled": True, "reply": str(exc), "context": _public_context(context), "rows": []}
    record_count = len(rows)
    if built_books and context.get("display_mode") == "excel" and record_count > 0:
        report_context = dict(context)
        if str(report_context.get("intent") or "") not in REPORT_INTENTS:
            report_context["complete"] = True
        saved = save_report(built_books, report_context, clock)
        if isinstance(saved, str):
            replies.append(saved)
        else:
            files.append({"name": str(saved["name"]), "path": str(saved["path"])})
            replies.append(f"Excel: {saved['path']}")
            context["excel_files"] = [str(saved["path"])]
            record_count = int(saved.get("records") or record_count)
    if context.get("delivery") == "EMAIL_REPORT" and context.get("display_mode") == "excel":
        replies.append(_email_report(text, [str(item) for item in list(context.get("excel_files") or [])], record_count))
    return {
        "handled": True,
        "reply": "\n\n".join(part for part in replies if part),
        "context": _public_context(context),
        "rows": rows,
        "files": files,
        "tables": tables,
        "table": tables[0] if len(tables) == 1 else None,
        "display_mode": context.get("display_mode") or "chat",
        "source": {"system": "odoo", "as_of": clock.isoformat()},
    }


def _email_report(text: str, paths: list[str], record_count: int) -> str:
    download = f" Download: {paths[0]}" if paths else ""
    recipients = email_addresses(text)
    if not recipients:
        return f"Email nahi gaya. Recipient email address likho.{download}"
    if not paths:
        return "Email nahi gaya. Bhejne ke liye Excel file nahi mili."
    problem = validate_for_email(paths, record_count)
    if problem:
        return f"Email nahi gaya. {problem}{download}"
    sent = send_excel_files(recipients, paths)
    if "bhej diya" not in sent:
        return f"{sent}{download}"
    return sent


def _attach_choices(result: dict[str, object]) -> dict[str, object]:
    result.setdefault("files", [])
    result.setdefault("tables", [])
    context = result.get("context") if isinstance(result.get("context"), dict) else {}
    if "display_mode" not in result:
        result["display_mode"] = context.get("display_mode") or "chat" if isinstance(context, dict) else "chat"
    candidates = list(context.get("candidates") or []) if isinstance(context, dict) else []
    if isinstance(context, dict) and context.get("pending") and candidates:
        result["suggestions"] = [
            str(item.get("label") or index)
            for index, item in enumerate(candidates, start=1)
            if isinstance(item, dict)
        ]
    else:
        result["suggestions"] = []
    return result
