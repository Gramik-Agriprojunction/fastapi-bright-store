"""Intent phrases. Earlier entries win, so specific phrases stay above general ones."""

from __future__ import annotations

PERIOD_INTENTS = {
    "today_sales",
    "date_range_sales",
    "stock_inward",
    "incoming_transfer",
    "stock_outward",
    "rto_received",
    "outgoing_transfer",
    "cancelled_qty",
    "lmd_picked_qty",
    "today_lmd_picked",
    "delivered_dc",
}

SNAPSHOT_INTENTS = {
    "current_stock",
    "on_hand_qty",
    "physical_stock",
    "expected_stock",
    "free_qty",
    "reserved_qty",
    "stock_variance",
    "reconciliation_difference",
    "reconciliation_status",
    "product_summary",
    "store_wise_stock",
    "in_transit",
    "rto_in_transit",
    "net_with_customers",
    "store_comparison",
}

INTENTS: list[dict[str, object]] = [
    {
        "code": "everything",
        "description": "On hand, sale out, RTO, In, DC In, and back together",
        "available": True,
        "phrases": [
            "sara kuch",
            "sare kuch",
            "sab kuch",
            "sab de do",
            "poora de do",
            "pura de do",
            "everything",
        ],
    },
    {
        "code": "back_received",
        "description": "RTO documents, stock that came back, one challan at a time",
        "available": True,
        "phrases": ["back"],
    },
    {
        "code": "lmd_picked_qty",
        "description": "LMD picked quantity",
        "available": False,
        "phrases": ["lmd", "pick kiya", "picking", "picked qty", "picked"],
    },
    {
        "code": "rto_in_transit",
        "description": "Return created and not yet received",
        "available": True,
        "phrases": ["rto in transit", "rto transit", "return in transit"],
    },
    {
        "code": "in_transit",
        "description": "Quantity sitting in the transit location",
        "available": True,
        "phrases": ["in transit", "transit"],
    },
    {
        "code": "stock_variance",
        "description": "Live on hand minus expected on hand",
        "available": True,
        "phrases": ["mismatch", "variance", "gap", "on hand minus", "on-hand minus"],
    },
    {
        "code": "expected_stock",
        "description": "IN minus delivered plus RTO",
        "available": True,
        "phrases": ["hona chahiye", "expected"],
    },
    {
        "code": "free_qty",
        "description": "On hand minus reserved. The sheet calls this available",
        "available": True,
        "phrases": ["free qty", "free quantity", "available qty", "available quantity", "free"],
    },
    {
        "code": "reserved_qty",
        "description": "Quantity reserved by outgoing deliveries",
        "available": True,
        "phrases": ["reserved", "reserve"],
    },
    {
        "code": "cancelled_qty",
        "description": "Cancelled delivery demand. Stock did not move",
        "available": True,
        "phrases": ["cancel"],
    },
    {
        "code": "outgoing_transfer",
        "description": "Assigned customer deliveries that are not validated",
        "available": True,
        "phrases": ["outgoing", "assigned", "assign"],
    },
    {
        "code": "rto_received",
        "description": "RTO quantity received back into the store",
        "available": True,
        "phrases": ["rto", "return", "wapas", "wapis"],
    },
    {
        "code": "stock_inward",
        "description": "Quantity received into BL-D/Stock",
        "available": True,
        "phrases": [
            "inward", "incoming", "ibt", "aaya", "aayi", "aaye",
            "receive", "receipt", "push", "in hua", "transfer in", "in transfer",
        ],
    },
    {
        "code": "net_with_customers",
        "description": "Delivered minus RTO",
        "available": True,
        "phrases": ["customers ke paas", "customer ke paas", "net sale"],
    },
    {
        "code": "stock_outward",
        "description": "Completed customer outward quantity, same rows as delivered sale",
        "available": True,
        "phrases": ["outward", "bahar gaya"],
    },
    {
        "code": "physical_stock",
        "description": "Physical quant at BL-D/Stock. Same source as live on hand",
        "available": True,
        "phrases": ["physical"],
    },
    {
        "code": "delivered_dc",
        "description": "Delivered delivery-challan count, product-wise qty sum, and qty by DC number",
        "available": True,
        "phrases": ["dc", "challan", "number wise", "numberwise"],
    },
    {
        "code": "date_range_sales",
        "description": "Delivered customer quantity. Not LMD and not outgoing",
        "available": True,
        "phrases": ["sale", "sales", "delivered", "delivery", "bika", "bikri", "becha"],
    },
    {
        "code": "store_comparison",
        "description": "Compare stores. This workbook has only one store",
        "available": True,
        "phrases": ["kis store", "zyada stock", "sabse zyada", "stock difference", "dono store"],
    },
    {
        "code": "product_summary",
        "description": "Reconciliation summary for this product",
        "available": True,
        "phrases": ["summary", "report", "poora hisaab", "hisab", "status"],
    },
    {
        "code": "on_hand_qty",
        "description": "Live quant at BL-D/Stock, or ledger running on hand for a past day",
        "available": True,
        "phrases": [
            "on hand", "on-hand", "onhand", "current stock", "live stock",
            "kitna hai", "kitni hai", "kitne hai", "kitne hain", "kitna hoga", "kitna pada", "pada hai",
            "stock", "qty", "quantity",
        ],
    },
]
