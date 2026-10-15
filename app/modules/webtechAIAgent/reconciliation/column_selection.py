"""Columns the user named, or the default columns for a complete report."""

from __future__ import annotations

from app.modules.webtechAIAgent.reconciliation.intent_mapping import soften

COLUMN_LABELS: dict[str, str] = {
    "order_number": "Order Number",
    "product_name": "Product Name",
    "sku": "SKU",
    "sale_out": "Sale Out",
    "rto_in": "RTO IN",
    "delivered_qty": "Delivered Qty",
    "order_date": "Order Date",
    "delivery_date": "Delivery Date",
    "transaction_date": "Transaction Date",
    "rto_receipt_date": "RTO Receipt Date",
    "document_number": "Document Number",
    "original_sale_document": "Original Sale Document",
    "rto_receipt_document": "RTO Receipt Document",
    "warehouse": "Warehouse",
    "transaction_state": "Transaction State",
    "delivery_status": "Delivery Status",
    "customer_name": "Customer Name",
    "incoming_transfer": "Incoming Transfer",
    "outgoing_transfer": "Outgoing Transfer",
    "on_hand_qty": "On Hand Qty",
    "reserved_qty": "Reserved Qty",
    "free_qty": "Free Qty",
    "expected_qty": "Expected Qty",
    "variance": "Variance",
    "destination": "Destination",
    "received_qty": "Received Qty",
    "cancelled_qty": "Cancelled Qty",
}

# Longer phrases first so "order date" is not read as "order number".
_PHRASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("order_date", ("order date", "order ki date")),
    ("delivery_date", ("delivery date", "deliver date", "delivered date")),
    ("rto_receipt_date", ("rto receipt date", "rto date", "receipt date")),
    ("transaction_date", ("transaction date", "movement date")),
    ("order_number", ("order number", "order no", "order num")),
    ("original_sale_document", ("original sale", "sale document")),
    ("rto_receipt_document", ("rto receipt document", "rto document", "receipt document")),
    ("document_number", ("document number", "document no", "doc number")),
    ("product_name", ("product name",)),
    ("sku", ("sku", "product code")),
    ("sale_out", ("sale out", "saleout")),
    ("rto_in", ("rto in", "rtoin")),
    ("delivered_qty", ("delivered qty", "delivered quantity")),
    ("received_qty", ("received qty", "received quantity", "receive qty")),
    ("on_hand_qty", ("on hand qty", "on hand", "onhand")),
    ("reserved_qty", ("reserved qty", "reserved")),
    ("free_qty", ("free qty", "free stock", "free quantity")),
    ("expected_qty", ("expected qty", "hona chahiye")),
    ("variance", ("variance", "gap")),
    ("incoming_transfer", ("incoming transfer",)),
    ("outgoing_transfer", ("outgoing transfer",)),
    ("transaction_state", ("transaction state", "txn state")),
    ("delivery_status", ("delivery status",)),
    ("customer_name", ("customer name",)),
    ("warehouse", ("warehouse",)),
    ("destination", ("destination",)),
)

INTENT_COLUMNS: dict[str, tuple[str, ...]] = {
    "SALES_LEDGER": (
        "order_number", "product_name", "sku", "transaction_date", "sale_out", "rto_in",
        "delivery_status", "document_number", "warehouse",
    ),
    "SALES_OUT_REPORT": (
        "order_number", "product_name", "sku", "transaction_date", "sale_out", "warehouse", "document_number",
    ),
    "DELIVERED_ORDERS": (
        "order_number", "order_date", "delivery_date", "product_name", "sku", "delivered_qty",
    ),
    "RTO_RECEIVED_REPORT": (
        "order_number", "original_sale_document", "rto_receipt_document", "order_date",
        "rto_receipt_date", "product_name", "sku", "received_qty", "warehouse", "transaction_state",
    ),
    "INCOMING_STOCK_REPORT": (
        "document_number", "product_name", "sku", "transaction_date", "incoming_transfer", "warehouse", "transaction_state",
    ),
    "OUTGOING_STOCK_REPORT": (
        "order_number", "document_number", "product_name", "sku", "outgoing_transfer",
        "transaction_state", "transaction_date", "warehouse", "destination",
    ),
    "IN_TRANSIT_REPORT": (
        "document_number", "product_name", "sku", "transaction_date", "incoming_transfer", "warehouse", "transaction_state",
    ),
    "CANCELLED_ORDERS_REPORT": (
        "order_number", "document_number", "product_name", "sku", "cancelled_qty", "transaction_state", "transaction_date", "warehouse",
    ),
    "LIVE_STOCK_REPORT": ("warehouse", "product_name", "sku", "on_hand_qty", "reserved_qty", "free_qty"),
    "STOCK_RECONCILIATION": (
        "product_name", "sku", "warehouse", "on_hand_qty", "expected_qty", "variance", "sale_out", "rto_in",
    ),
    "PRODUCT_STOCK_SUMMARY": (
        "product_name", "sku", "warehouse", "on_hand_qty", "reserved_qty", "free_qty", "expected_qty", "variance",
    ),
}

_QTY_ALIAS = {
    "DELIVERED_ORDERS": "delivered_qty",
    "SALES_OUT_REPORT": "sale_out",
    "SALES_LEDGER": "sale_out",
    "RTO_RECEIVED_REPORT": "received_qty",
    "INCOMING_STOCK_REPORT": "incoming_transfer",
    "OUTGOING_STOCK_REPORT": "outgoing_transfer",
    "IN_TRANSIT_REPORT": "incoming_transfer",
    "CANCELLED_ORDERS_REPORT": "cancelled_qty",
}

_COMPLETE = (
    "koi bhi field", "sabhi field", "all field", "all column", "complete ledger",
    "poora ledger", "pura ledger", "pure sale", "sara ledger", "saara ledger",
)

# Values the stock movement does not carry. The column stays blank when requested.
UNAVAILABLE_ON_MOVE = {"order_date"}


def select_columns(text: str, intent: str | None) -> tuple[list[str], bool]:
    hay = soften(text)
    defaults = list(INTENT_COLUMNS.get(intent or "", ()))
    if any(phrase in hay for phrase in _COMPLETE) or (intent == "SALES_LEDGER" and "ledger" in hay and not _named(hay)):
        return defaults, False
    named = _named(hay)
    if "quantity" in hay or re_qty(hay):
        alias = _QTY_ALIAS.get(intent or "")
        if alias and alias not in named:
            named.append(alias)
    if not named:
        return defaults, False
    return named, True


def re_qty(hay: str) -> bool:
    return " qty" in f" {hay}" or hay.endswith(" qty") or "quantity" in hay


def _named(hay: str) -> list[str]:
    found: list[str] = []
    used: set[str] = set()
    for key, phrases in _PHRASES:
        if key in used:
            continue
        if any(phrase in hay for phrase in phrases):
            found.append(key)
            used.add(key)
    return found


def labels(columns: list[str]) -> list[str]:
    return [COLUMN_LABELS.get(key, key) for key in columns]
