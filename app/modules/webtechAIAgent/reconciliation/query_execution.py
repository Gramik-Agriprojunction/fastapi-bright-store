"""Deterministic inventory rows. Totals come from the ledger, not from a model."""

from __future__ import annotations

from datetime import date

from app.modules.webtechAIAgent.reconciliation.answer_formatting import stock_card
from app.modules.webtechAIAgent.reconciliation.column_selection import (
    COLUMN_LABELS,
    INTENT_COLUMNS,
    UNAVAILABLE_ON_MOVE,
    labels,
    select_columns,
)
from app.modules.webtechAIAgent.reconciliation.intent_mapping import REPORT_INTENTS, soften
from app.modules.webtechAIAgent.reconciliation.inventory_query import (
    expected_until,
    period_bounds,
    pretty,
    qty,
)
from app.modules.webtechAIAgent.reconciliation.workbook import Book, Move

SHOW_LIMIT = 20
PAGE_SIZE = 20
EMPTY = "No matching records found"
_OPEN_PENDING = {"confirmed", "waiting", "partially_available", "draft"}
_NUMERIC = {
    "sale_out", "rto_in", "delivered_qty", "received_qty", "incoming_transfer",
    "outgoing_transfer", "on_hand_qty", "reserved_qty", "free_qty", "expected_qty",
    "variance", "cancelled_qty",
}


def execute_report(book: Book, context: dict[str, object], today: date) -> dict[str, object]:
    intent = str(context.get("intent") or "")
    message = str(context.get("message") or "")
    columns, explicit = select_columns(message, intent)
    if not explicit and not columns:
        columns = list(INTENT_COLUMNS.get(intent, ()))
    stored = context.get("columns")
    if isinstance(stored, list) and stored:
        columns = [str(item) for item in stored]
    missing = [COLUMN_LABELS[key] for key in columns if key in UNAVAILABLE_ON_MOVE]
    if intent == "LIVE_STOCK_REPORT":
        return _live(book, columns, missing)
    if intent in {"PRODUCT_STOCK_SUMMARY", "STOCK_RECONCILIATION"}:
        end = book.snapshot
        date_filter = context.get("date_filter") if isinstance(context.get("date_filter"), dict) else None
        if isinstance(date_filter, dict) and date_filter.get("type") not in {None, "current", "all"}:
            bounds = period_bounds(book, date_filter, today)
            if isinstance(bounds, str):
                return {"reply": bounds, "rows": [], "tables": [], "record_count": 0}
            end = bounds[1]
        return _summary(book, intent, columns, missing, end)
    date_filter = context.get("date_filter") if isinstance(context.get("date_filter"), dict) else {"type": "all"}
    bounds = period_bounds(book, date_filter, today)
    if isinstance(bounds, str):
        return {"reply": bounds, "rows": [], "tables": [], "record_count": 0}
    moves = _dedupe([row for row in book.moves if bounds[0] <= row.when.date() <= bounds[1]])
    page = max(1, int(context.get("page") or 1))
    if intent == "SALES_LEDGER":
        records = _sales_ledger(book, moves)
        title = "Sales ledger"
    elif intent == "SALES_OUT_REPORT":
        records = _sales_ledger(book, [row for row in moves if row.bucket == "Delivered" and _done(row)])
        title = "Sale out"
    elif intent == "DELIVERED_ORDERS":
        records = [_delivered(book, row) for row in moves if row.bucket == "Delivered" and _done(row)]
        title = "Delivered orders"
    elif intent == "RTO_RECEIVED_REPORT":
        records = [_rto(book, row) for row in moves if row.bucket == "RTO" and _done(row)]
        title = "RTO received"
    elif intent == "INCOMING_STOCK_REPORT":
        records = [_incoming(book, row) for row in moves if row.bucket == "IN" and _done(row)]
        title = "Incoming stock"
    elif intent == "OUTGOING_STOCK_REPORT":
        return _outgoing(book, moves, columns, missing, bounds, soften(message), page)
    elif intent == "IN_TRANSIT_REPORT":
        records = _transit(book, moves)
        title = "In transit"
    elif intent == "CANCELLED_ORDERS_REPORT":
        records = [_cancelled(book, row) for row in moves if row.bucket == "Cancelled"]
        title = "Cancelled orders"
    else:
        return {"reply": f"{intent} in buckets se verify nahi ho saka.", "rows": [], "tables": [], "record_count": 0}
    return _table_result(book, title, columns, records, missing, bounds, page)


def _live(book: Book, columns: list[str], missing: list[str]) -> dict[str, object]:
    record = _stock_record(book, book.snapshot)
    reply = stock_card(
        location=book.warehouse or book.store_name,
        product_name=book.product_name,
        sku=book.sku,
        variant=book.variant,
        updated_at=book.stock_updated_at,
        snapshot=book.snapshot,
        on_hand=book.live_on_hand,
        reserved=book.live_reserved,
        incoming=book.incoming_qty,
    )
    table = _sheet("Live Stock", columns, [record])
    return {
        "reply": _with_missing(reply, missing),
        "rows": [record],
        "tables": [table],
        "record_count": 1 if book.live_on_hand is not None else 0,
    }


def _summary(book: Book, intent: str, columns: list[str], missing: list[str], end: date) -> dict[str, object]:
    record = _stock_record(book, end)
    record["sale_out"] = _sum_bucket(book, "Delivered", "qty_out", end)
    record["rto_in"] = _sum_bucket(book, "RTO", "qty_in", end)
    title = "Stock reconciliation" if intent == "STOCK_RECONCILIATION" else "Product stock"
    lines = [
        f"{book.product_name} (SKU {book.sku}) — {title}",
        f"{book.store_name} — {book.warehouse}",
        f"On Hand is physical stock at {book.location or book.warehouse}.",
    ]
    for key in columns:
        lines.append(f"{COLUMN_LABELS.get(key, key)}: {_show(record.get(key))}")
    table = _sheet("Summary" if intent == "STOCK_RECONCILIATION" else "Summary", columns, [record])
    live = _sheet("Live Stock", ["warehouse", "product_name", "sku", "on_hand_qty", "reserved_qty", "free_qty"], [record])
    return {
        "reply": _with_missing("\n".join(lines), missing),
        "rows": [record],
        "tables": [table, live],
        "record_count": 1,
    }


def _outgoing(
    book: Book,
    moves: list[Move],
    columns: list[str],
    missing: list[str],
    bounds: tuple[date, date],
    hay: str,
    page: int,
) -> dict[str, object]:
    groups = _outgoing_groups(hay)
    sections: list[tuple[str, list[dict[str, object]]]] = []
    for status in ("pending", "assigned", "completed", "cancelled"):
        if status not in groups:
            continue
        if status == "cancelled":
            picked = [_cancelled(book, row) for row in moves if row.bucket == "Cancelled"]
        elif status == "completed":
            picked = [
                _outgoing_row(book, row, "completed")
                for row in moves
                if row.bucket == "Outgoing" and row.state.lower() == "done"
            ]
        else:
            picked = [
                _outgoing_row(book, row, status)
                for row in moves
                if row.bucket == "Outgoing" and _outgoing_status(row.state) == status
            ]
        sections.append((status, picked))
    lines = [
        f"{book.product_name} (SKU {book.sku}) — Outgoing stock",
        f"{book.store_name} — {book.warehouse}",
        f"Period {bounds[0].isoformat()} se {bounds[1].isoformat()}",
        "Pending, assigned, completed, and cancelled are separate. Their quantities are not added together.",
    ]
    rows: list[dict[str, object]] = []
    for status, picked in sections:
        amount = sum(float(row.get("outgoing_transfer") or row.get("cancelled_qty") or 0) for row in picked)
        lines.append(f"{status}: {len(_orders(picked))} orders · {qty(amount)} qty")
        rows.extend(picked)
    chat = _chat_table("Outgoing stock", columns, rows, page)
    lines.append(EMPTY if not rows else _preview_line(chat))
    sheet = _sheet("Outgoing Stock", columns, rows)
    return {
        "reply": _with_missing("\n".join(line for line in lines if line), missing),
        "rows": rows,
        "tables": [sheet],
        "table": chat,
        "record_count": len(rows),
    }


def _table_result(
    book: Book,
    title: str,
    columns: list[str],
    records: list[dict[str, object]],
    missing: list[str],
    bounds: tuple[date, date],
    page: int,
) -> dict[str, object]:
    orders = _orders(records)
    lines = [
        f"{book.product_name} (SKU {book.sku}) — {title}",
        f"{book.store_name} — {book.warehouse}",
        f"Period {bounds[0].isoformat()} se {bounds[1].isoformat()}",
        f"Orders {len(orders)} · rows {len(records)}",
    ]
    for key in columns:
        if key not in _NUMERIC:
            continue
        lines.append(f"{COLUMN_LABELS[key]} total {qty(_total(records, key))}")
    chat_columns = columns
    chat_title = title
    if title == "RTO received":
        chat_columns = ["received_qty"]
        chat_title = "RTO"
    chat = _chat_table(chat_title, chat_columns, records, page)
    lines.append(EMPTY if not records else _preview_line(chat))
    sheet = "Sales Ledger" if title in {"Sales ledger", "Sale out"} else {
        "Delivered orders": "Delivered Orders",
        "RTO received": "RTO Received",
        "Incoming stock": "Incoming Stock",
        "In transit": "In Transit",
        "Cancelled orders": "Cancelled Orders",
    }.get(title, title)
    tables = [_sheet(sheet, columns, records)]
    if sheet == "Sales Ledger":
        tables.insert(0, _sheet("Summary", columns, records))
    return {
        "reply": _with_missing("\n".join(lines), missing),
        "rows": records,
        "tables": tables,
        "table": chat,
        "record_count": len(records),
    }


def _chat_table(title: str, columns: list[str], records: list[dict[str, object]], page: int) -> dict[str, object]:
    page = max(1, int(page or 1))
    start = (page - 1) * PAGE_SIZE
    # Page 1 is the latest day, so 15 Oct is not hidden behind older rows.
    shown = list(reversed(records))[start:start + PAGE_SIZE]
    return {
        "title": title,
        "columns": labels(columns),
        "rows": [{COLUMN_LABELS.get(key, key): _cell_text(record.get(key)) for key in columns} for record in shown],
        "record_count": len(records),
        "page": page,
        "page_size": PAGE_SIZE,
        "from": (start + 1) if shown else 0,
        "to": start + len(shown),
        "totals": {
            COLUMN_LABELS[key]: qty(_total(records, key))
            for key in columns
            if key in _NUMERIC
        },
    }


def _preview_line(table: dict[str, object]) -> str:
    count = int(table.get("record_count") or 0)
    if count == 0:
        return EMPTY
    if count <= PAGE_SIZE and int(table.get("page") or 1) == 1:
        return f"Showing {count} of {count} records."
    return f"Showing {table['from']}-{table['to']} of {count} records."


def _cell_text(value: object) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)):
        return qty(float(value))
    return str(value)


def _sheet(name: str, columns: list[str], records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "sheet": name,
        "columns": columns,
        "headers": labels(columns),
        "records": records,
    }


def _sales_ledger(book: Book, moves: list[Move]) -> list[dict[str, object]]:
    grouped: dict[str, list[Move]] = {}
    for row in moves:
        if row.bucket == "Delivered" and _done(row):
            grouped.setdefault(_order_key(row), []).append(row)
        elif row.bucket == "RTO" and _done(row):
            grouped.setdefault(_order_key(row), []).append(row)
    records = []
    for key in sorted(grouped):
        bundle = grouped[key]
        delivered = [row for row in bundle if row.bucket == "Delivered"]
        returned = [row for row in bundle if row.bucket == "RTO"]
        records.append(
            {
                "order_number": key,
                "product_name": book.product_name,
                "sku": book.sku,
                "warehouse": book.warehouse or book.store_name,
                "transaction_date": _day(min(row.when for row in bundle)),
                "order_date": None,
                "delivery_date": _day(max(row.when for row in delivered)) if delivered else None,
                "rto_receipt_date": _day(max(row.when for row in returned)) if returned else None,
                "sale_out": sum(row.qty_out or 0 for row in delivered),
                "rto_in": sum(row.qty_in or 0 for row in returned),
                "delivered_qty": sum(row.qty_out or 0 for row in delivered),
                "delivery_status": _states(delivered),
                "transaction_state": _states(bundle),
                "document_number": _docs(bundle),
                "original_sale_document": key,
                "customer_name": _partners(bundle),
            }
        )
    return records


def _delivered(book: Book, row: Move) -> dict[str, object]:
    return {
        "order_number": _order_key(row),
        "product_name": book.product_name,
        "sku": book.sku,
        "warehouse": book.warehouse or book.store_name,
        "order_date": None,
        "delivery_date": _day(row.when),
        "transaction_date": _day(row.when),
        "delivered_qty": row.qty_out or 0,
        "sale_out": row.qty_out or 0,
        "document_number": row.doc,
        "transaction_state": row.state,
        "delivery_status": row.state,
        "customer_name": row.partner,
    }


def _rto(book: Book, row: Move) -> dict[str, object]:
    return {
        "order_number": row.sale or row.return_of or "",
        "product_name": book.product_name,
        "sku": book.sku,
        "warehouse": book.warehouse or book.store_name,
        "order_date": None,
        "rto_receipt_date": _day(row.when),
        "transaction_date": _day(row.when),
        "original_sale_document": row.sale or row.return_of,
        "rto_receipt_document": row.doc,
        "document_number": row.doc,
        "received_qty": row.qty_in or 0,
        "rto_in": row.qty_in or 0,
        "transaction_state": row.state,
        "customer_name": row.partner,
    }


def _incoming(book: Book, row: Move) -> dict[str, object]:
    return {
        "document_number": row.doc,
        "order_number": row.sale,
        "product_name": book.product_name,
        "sku": book.sku,
        "warehouse": book.warehouse or book.store_name,
        "transaction_date": _day(row.when),
        "incoming_transfer": row.qty_in or 0,
        "transaction_state": row.state,
        "destination": row.dest,
    }


def _outgoing_row(book: Book, row: Move, status: str) -> dict[str, object]:
    return {
        "order_number": _order_key(row),
        "document_number": row.doc,
        "product_name": book.product_name,
        "sku": book.sku,
        "warehouse": book.warehouse or book.store_name,
        "transaction_date": _day(row.when),
        "outgoing_transfer": row.qty_out or row.demand or 0,
        "transaction_state": status,
        "destination": row.dest,
        "customer_name": row.partner,
    }


def _cancelled(book: Book, row: Move) -> dict[str, object]:
    return {
        "order_number": _order_key(row),
        "document_number": row.doc,
        "product_name": book.product_name,
        "sku": book.sku,
        "warehouse": book.warehouse or book.store_name,
        "transaction_date": _day(row.when),
        "cancelled_qty": row.demand if row.demand is not None else 0,
        "outgoing_transfer": 0,
        "transaction_state": "cancelled",
        "customer_name": row.partner,
    }


def _transit(book: Book, moves: list[Move]) -> list[dict[str, object]]:
    records = [
        _incoming(book, row)
        for row in moves
        if row.bucket in {"In transit", "Transit leg", "RTO in transit"} and row.state.lower() != "done"
    ]
    for record in records:
        record["transaction_state"] = record.get("transaction_state") or "in transit"
    if book.transit_on_hand is not None and not records:
        records.append(
            {
                "document_number": "TRANSIT LOCATION NOW",
                "product_name": book.product_name,
                "sku": book.sku,
                "warehouse": book.warehouse or book.store_name,
                "transaction_date": pretty(book.snapshot) if book.snapshot else None,
                "incoming_transfer": book.transit_on_hand,
                "transaction_state": "on hand",
            }
        )
    elif book.transit_on_hand and records:
        records.append(
            {
                "document_number": "TRANSIT LOCATION NOW",
                "product_name": book.product_name,
                "sku": book.sku,
                "warehouse": book.warehouse or book.store_name,
                "transaction_date": pretty(book.snapshot) if book.snapshot else None,
                "incoming_transfer": book.transit_on_hand,
                "transaction_state": "on hand",
            }
        )
    return records


def _stock_record(book: Book, end: date) -> dict[str, object]:
    on_hand = book.live_on_hand
    reserved = book.live_reserved
    if on_hand is None or reserved is None:
        free = book.live_free
    else:
        free = on_hand - reserved
    expected = expected_until(book, end) if book.moves or book.first_day else None
    variance = (on_hand - expected) if on_hand is not None and expected is not None else None
    return {
        "product_name": book.product_name,
        "sku": book.sku,
        "warehouse": book.warehouse or book.store_name,
        "on_hand_qty": on_hand,
        "reserved_qty": reserved,
        "free_qty": free,
        "expected_qty": expected,
        "variance": variance,
    }


def _sum_bucket(book: Book, bucket: str, field: str, end: date) -> float:
    total = 0.0
    seen: set[tuple[object, ...]] = set()
    for row in book.moves:
        if row.bucket != bucket or row.when.date() > end or not _done(row):
            continue
        key = (row.doc, row.bucket, row.sale, getattr(row, field), row.when.isoformat())
        if key in seen:
            continue
        seen.add(key)
        total += float(getattr(row, field) or 0)
    return total


def _outgoing_groups(hay: str) -> set[str]:
    if any(phrase in hay for phrase in ("completed", "done outgoing")):
        return {"completed"}
    if "cancel" in hay and "outgoing" in hay:
        return {"cancelled"}
    if any(phrase in hay for phrase in ("abhi", "jane wala", "jaane wala", "ja raha", "current")):
        return {"assigned", "pending"}
    return {"assigned", "pending"}


def _outgoing_status(state: str) -> str:
    value = (state or "").lower()
    if value == "assigned":
        return "assigned"
    if value in _OPEN_PENDING:
        return "pending"
    if value == "done":
        return "completed"
    if value == "cancel":
        return "cancelled"
    return "pending"


def _dedupe(moves: list[Move]) -> list[Move]:
    seen: set[tuple[object, ...]] = set()
    kept: list[Move] = []
    for row in moves:
        key = (row.doc, row.bucket, row.sale, row.qty_in, row.qty_out, row.when.isoformat(), row.state, row.demand)
        if key in seen:
            continue
        seen.add(key)
        kept.append(row)
    return kept


def _done(row: Move) -> bool:
    return row.state.lower() == "done"


def _order_key(row: Move) -> str:
    return row.sale.strip() or row.doc


def _day(when: object) -> str:
    return pretty(when.date()) if hasattr(when, "date") else ""


def _docs(rows: list[Move]) -> str:
    found: list[str] = []
    for row in rows:
        if row.doc and row.doc not in found:
            found.append(row.doc)
    return ", ".join(found)


def _partners(rows: list[Move]) -> str:
    found: list[str] = []
    for row in rows:
        if row.partner and row.partner not in found:
            found.append(row.partner)
    return ", ".join(found)


def _states(rows: list[Move]) -> str | None:
    found: list[str] = []
    for row in rows:
        if row.state and row.state not in found:
            found.append(row.state)
    return ", ".join(found) if found else None


def _orders(records: list[dict[str, object]]) -> list[str]:
    found: list[str] = []
    for record in records:
        key = str(record.get("order_number") or record.get("document_number") or "")
        if key and key not in found:
            found.append(key)
    return found


def _total(records: list[dict[str, object]], key: str) -> float:
    total = 0.0
    for record in records:
        value = record.get(key)
        if isinstance(value, (int, float)):
            total += float(value)
    return total


def _show(value: object) -> str:
    if value is None or value == "":
        return "blank"
    if isinstance(value, (int, float)):
        return qty(float(value))
    return str(value)


def _block(columns: list[str], record: dict[str, object]) -> str:
    body = "\n".join(f"{COLUMN_LABELS.get(key, key)}: {_show(record.get(key))}" for key in columns)
    return f"\n{body}"


def _with_missing(reply: str, missing: list[str]) -> str:
    if not missing:
        return reply
    note = (
        f"{', '.join(missing)} is not stored on the stock movement, so that column is blank."
    )
    return f"{reply}\n{note}"


__all__ = ["REPORT_INTENTS", "execute_report"]
