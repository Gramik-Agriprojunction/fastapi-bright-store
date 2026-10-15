"""Plain-text answers. The chat renders this as text, not a markdown table."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.modules.webtechAIAgent.reconciliation.inventory_query import pretty, qty
from app.modules.webtechAIAgent.reconciliation.workbook import Book

IST = ZoneInfo("Asia/Kolkata")


def product_line(book: Book) -> str:
    return f"{book.product_name} (SKU {book.sku})"


def store_line(book: Book) -> str:
    return f"{book.store_name} — {book.warehouse}"


def snapshot_line(book: Book) -> str:
    lot = f" · lot {book.lot}" if book.lot else ""
    return f"Live stock · {pretty(book.snapshot)} IST · {book.location}{lot}"


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def format_stock_updated(when: datetime | None, snapshot: date | None) -> str:
    stamp = when
    if stamp is None and snapshot is not None:
        stamp = datetime(snapshot.year, snapshot.month, snapshot.day, 0, 0, tzinfo=IST)
    if stamp is None:
        return ""
    local = stamp.astimezone(IST) if stamp.tzinfo else stamp.replace(tzinfo=IST)
    hour = local.hour % 12 or 12
    suffix = "AM" if local.hour < 12 else "PM"
    return f"{local.day} {_MONTHS[local.month - 1]} {local.year}, {hour}:{local.minute:02d} {suffix}"


def _product_title(product_name: str, variant: str) -> str:
    title = product_name.strip()
    pack = variant.strip()
    if pack and title.endswith(f"({pack})"):
        title = title[: -(len(pack) + 2)].strip()
    return title


def stock_card(
    *,
    location: str,
    product_name: str,
    sku: str,
    variant: str,
    updated_at: datetime | None,
    snapshot: date | None,
    on_hand: float | None,
    reserved: float | None,
    incoming: float | None,
) -> str:
    """User-facing stock block. Labels stay in this order and nothing else is added."""
    free = (on_hand - reserved) if on_hand is not None and reserved is not None else 0
    title = _product_title(product_name, variant)
    product = f"{title} (SKU {sku})" if sku else title
    fields = [
        ("Location", location),
        ("Product", product),
        ("Variant", variant.strip()),
        ("Stock Updated At", format_stock_updated(updated_at, snapshot)),
        ("On Hand", qty(0 if on_hand is None else on_hand)),
        ("Reserved", qty(0 if reserved is None else reserved)),
        ("Free", qty(free)),
        ("Incoming", qty(0 if incoming is None else incoming)),
    ]
    return "\n\n".join(f"{label}\n{value}" for label, value in fields)


def lines(*parts: str) -> str:
    return "\n".join(part for part in parts if part)


def document_lines(rows: list[dict[str, object]]) -> str:
    if not rows:
        return ""
    shown = list(reversed(rows))[:40]
    body = "\n".join(
        f"{row['date']} · {row['doc']} · {row['customer'] or '—'} · {qty(row['qty'] if isinstance(row['qty'], (int, float)) else None)}"
        for row in shown
    )
    extra = ""
    if len(rows) > len(shown):
        extra = f"\nAur {len(rows) - len(shown)} documents hain."
    return body + extra
