"""Calculations taken from the workbook rules. Sales are not LMD picks."""

from __future__ import annotations

from datetime import date, timedelta

from app.modules.webtechAIAgent.reconciliation.workbook import Book, Move

SALES = "Delivered"
INWARD = "IN"
RTO = "RTO"
OUTGOING = "Outgoing"
CANCELLED = "Cancelled"


def qty(value: float | None) -> str:
    if value is None:
        return "blank"
    rounded = round(value, 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def pretty(day: date) -> str:
    return f"{day.day} {day.strftime('%b')} {day.year}"


def period_bounds(book: Book, date_filter: dict[str, object] | None, today: date) -> tuple[date, date] | str:
    kind = (date_filter or {}).get("type")
    if kind in {None, "all", "current"}:
        if book.first_day is None or book.last_day is None:
            return "Ledger mein koi movement date nahi hai."
        return book.first_day, book.last_day
    start = date.fromisoformat(str(date_filter["start"]))
    end = date.fromisoformat(str(date_filter["end"]))
    if book.snapshot and start > book.snapshot:
        return (
            f"Stock moves {pretty(book.snapshot)} tak hain. "
            f"{pretty(start)} se {pretty(end)} abhi verify nahi ho sakta."
        )
    if book.first_day and end < book.first_day:
        return (
            f"Pehli stock movement {pretty(book.first_day)} ki hai. "
            f"{pretty(start)} se pehle ka stock movement nahi mila."
        )
    return start, end


def _between(row: Move, start: date, end: date) -> bool:
    day = row.when.date()
    return start <= day <= end


def _sum(rows: list[Move], field: str) -> float:
    total = 0.0
    for row in rows:
        value = getattr(row, field)
        if value is not None:
            total += value
    return total


def movements(book: Book, bucket: str, start: date, end: date) -> list[Move]:
    return [row for row in book.moves if row.bucket == bucket and _between(row, start, end)]


def cumulative(book: Book, bucket: str, end: date) -> list[Move]:
    return [row for row in book.moves if row.bucket == bucket and row.when.date() <= end]


def expected_until(book: Book, end: date) -> float:
    inward = _sum(cumulative(book, INWARD, end), "qty_in")
    adjustment_in = _sum(cumulative(book, "Adjustment IN", end), "qty_in")
    sold = _sum(cumulative(book, SALES, end), "qty_out")
    adjustment_out = _sum(cumulative(book, "Adjustment OUT", end), "qty_out")
    returned = _sum(cumulative(book, RTO, end), "qty_in")
    return inward + adjustment_in + returned - sold - adjustment_out


def running_until(book: Book, end: date) -> Move | None:
    rows = [
        row for row in book.moves
        if row.running is not None and row.when.date() <= end
    ]
    return rows[-1] if rows else None


def open_rto(book: Book) -> list[Move]:
    return [row for row in book.moves if row.bucket == RTO and row.state.lower() != "done"]


def document_row(row: Move, amount: float | None) -> dict[str, object]:
    return {
        "date": pretty(row.when.date()),
        "doc": row.doc,
        "sale": row.sale,
        "customer": row.partner,
        "qty": amount,
        "bucket": row.bucket,
    }


def outside_snapshot(book: Book, today: date, date_filter: dict[str, object] | None) -> str | None:
    kind = (date_filter or {}).get("type")
    if kind == "today" and today > book.snapshot:
        return (
            f"Aaj {pretty(today)} hai. Stock moves {pretty(book.snapshot)} tak load hue hain, "
            "isliye uske baad ki quantity verify nahi ho sakti."
        )
    if kind == "yesterday":
        yesterday = today - timedelta(days=1)
        if yesterday > book.snapshot:
            return (
                f"Kal {pretty(yesterday)} bhi snapshot {pretty(book.snapshot)} ke baad ka din hai."
            )
    return None
