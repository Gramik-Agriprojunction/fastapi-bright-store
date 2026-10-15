"""Read-only stock questions for the inventory-register chat.

Numbers use the same buckets as the dark-store reconciliation sheet.
Nothing here writes to Odoo.
"""

from __future__ import annotations

import calendar
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import get_settings

LIVE_JSON2 = "https://com.gramik.in/json/2"
# List and get only. Create, write, unlink, drop, and update never leave this process.
READ_METHODS = frozenset({"search_read", "read", "search", "search_count", "name_search", "fields_get"})
OdooId = int | bool | list[Any] | dict[str, Any] | None

STOP = {
    "kitna", "kitni", "hua", "hue", "hai", "hain", "mein", "me", "mai", "main",
    "dark", "store", "warehouse", "darkstore", "month", "mahine", "order", "orders",
    "list", "qty", "quantity", "aur", "and", "the", "how", "much", "what", "ka",
    "ki", "ke", "se", "pe", "par", "do", "dena", "bhejo", "batao", "bata", "of",
    "for", "in", "on", "to", "from", "a", "an", "ya", "yaa", "please", "total",
    "successful", "sale", "push", "receive", "received", "aaya", "aayi", "aaye",
    "delivered", "delivery", "deliver", "rto", "transit", "outgoing", "october",
    "oct", "september", "sep", "november", "nov", "december", "dec", "january",
    "jan", "february", "feb", "march", "mar", "april", "apr", "may", "june", "jun",
    "july", "jul", "august", "aug", "this", "is", "was", "were", "with", "sheet",
    "hona", "chahiye", "live", "hand", "stock", "product", "products", "name",
    "wala", "wali", "wale", "kaun", "konsa", "which",     "show", "dikhao", "nikalo",
    "tak", "count", "number", "numbers", "wise", "sum", "ab", "dc", "challan", "numberwise",
}

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

PLACE_TOKENS = {"barabanki", "fatehpur", "hardoi", "unnao"}
OPEN_STATES = {"assigned", "confirmed", "waiting", "partially_available"}
PRODUCT_FREE_BUCKETS = {"Delivered", "IN", "RTO", "Outgoing", "Cancelled", "Adjustment"}
MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

warehouse_cache: dict[str, Any] | None = None


@dataclass
class Warehouse:
    id: int
    name: str
    code: str
    stock_id: int
    stock_name: str
    transit_id: int | None


@dataclass
class ProductRow:
    id: int
    name: str
    sku: str
    label: str


@dataclass
class MoveRow:
    when: str | None
    doc: str
    bucket: str
    state: str
    sale: str
    customer: str
    qty: float
    demand: float
    source: str = ""
    dest: str = ""


def norm(value: str) -> str:
    text = value.lower().replace("lavkhush", "lavkush").replace("luvkush", "lavkush")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def m2o_id(value: OdooId) -> int | None:
    if isinstance(value, list) and value:
        return int(value[0]) or None
    if isinstance(value, dict) and "id" in value:
        return int(value["id"]) or None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def m2o_name(value: OdooId) -> str:
    if isinstance(value, list) and len(value) > 1:
        return str(value[1] or "")
    if isinstance(value, dict) and value.get("display_name"):
        return str(value["display_name"])
    return ""


def partner_name(value: OdooId) -> str:
    return m2o_name(value).split(",")[0].strip()


def odoo_target() -> tuple[str, str]:
    settings = get_settings()
    env_key = (settings.odoo_crm_api_key or "").strip()
    explicit = (settings.odoo_json2_url or "").strip().rstrip("/")
    base = (settings.odoo_crm_base_url or "").strip().rstrip("/")
    local = not base or bool(re.search(r"127\.0\.0\.1|localhost", base, re.IGNORECASE))
    if explicit:
        return explicit, env_key
    if not local:
        root = base.removesuffix("/api")
        return f"{root}/json/2", env_key
    return LIVE_JSON2, env_key


def odoo(model: str, method: str, payload: dict[str, Any]) -> Any:
    if method not in READ_METHODS:
        raise RuntimeError(f"Stock read sirf list/get karta hai. '{method}' allowed nahi hai.")
    url, key = odoo_target()
    if not key:
        raise RuntimeError("Stock read key configured nahi hai.")
    request = urllib.request.Request(
        f"{url}/{model}/{method}",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "gramik-webtech-agent",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:180]
        raise RuntimeError(f"Stock read {exc.code}: {detail}") from exc


# Moves, pickings, and quants keep paging until Odoo runs out.
# A fixed oldest-first cap dropped today's rows once history passed 4000.
EXHAUST_MODELS = frozenset({"stock.move", "stock.move.line", "stock.picking", "stock.quant"})
READ_SAFETY = 100_000


def search_read_all(
    model: str,
    domain: list[Any],
    fields: list[str],
    order: str = "id asc",
    limit: int | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    page = 200
    if limit is not None:
        cap = max(limit, 0)
    elif model in EXHAUST_MODELS:
        cap = READ_SAFETY
    else:
        cap = 4000
    while len(rows) < cap:
        batch = odoo(
            model,
            "search_read",
            {
                "domain": domain,
                "fields": fields,
                "context": {"active_test": False, "lang": "en_US"},
                "limit": min(page, cap - len(rows)),
                "offset": offset,
                "order": order,
            },
        )
        if not isinstance(batch, list):
            break
        rows.extend(batch)
        if len(batch) < page:
            return rows
        offset += page
    return rows


def ist_date_key(value: Any) -> str | None:
    if not value or value is False:
        return None
    text = str(value).split(".")[0].replace("T", " ")
    match = re.match(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})", text)
    if not match:
        return None
    utc = datetime.strptime(f"{match.group(1)} {match.group(2)}", "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=UTC
    )
    return (utc + timedelta(minutes=330)).date().isoformat()


def format_in(iso: str | None) -> str:
    if not iso:
        return ""
    year, month, day = iso.split("-")
    return f"{int(day)} {MONTH_LABELS[int(month) - 1]} {year}"


def is_return(move: dict[str, Any], picking: dict[str, Any] | None) -> bool:
    if m2o_id(move.get("origin_returned_move_id")):
        return True
    if picking and m2o_id(picking.get("return_id")):
        return True
    origin = str((picking or {}).get("origin") or move.get("origin") or "")
    return origin.lower().startswith("return of ")


def qty_of(move: dict[str, Any]) -> float:
    done = float(move.get("quantity") or 0)
    demand = float(move.get("product_uom_qty") or 0)
    state = move.get("state")
    if state == "cancel":
        return 0
    if state == "done":
        return done
    return done or demand


def classify(
    move: dict[str, Any],
    picking: dict[str, Any] | None,
    usage: dict[int, str],
    stock_id: int,
    transit_id: int | None,
) -> str:
    src = m2o_id(move.get("location_id"))
    dest = m2o_id(move.get("location_dest_id"))
    state = str(move.get("state") or "")
    src_usage = usage.get(src or 0, "")
    dest_usage = usage.get(dest or 0, "")
    returned = is_return(move, picking)
    into = dest == stock_id and src != stock_id
    out = src == stock_id and dest != stock_id

    if state == "cancel":
        return "Cancelled" if into or out else ""
    if state == "done":
        if into and returned:
            return "RTO"
        if into and src_usage == "inventory":
            return "Adjustment IN"
        if into:
            return "IN"
        if out and dest_usage == "customer" and not returned:
            return "Delivered"
        if out and dest_usage == "inventory":
            return "Adjustment OUT"
        if out:
            return "Other OUT"
        if transit_id and dest == transit_id and src != stock_id:
            return "Transit leg"
        return ""
    if state in OPEN_STATES:
        if into and returned:
            return "RTO in transit"
        if out and dest_usage == "customer":
            return "Outgoing"
        if transit_id and (dest == transit_id or src == transit_id or into):
            return "In transit"
        if out:
            return "Outgoing"
    return ""


def load_warehouses() -> list[Warehouse]:
    global warehouse_cache
    if warehouse_cache and datetime.now(UTC).timestamp() - warehouse_cache["at"] < 10 * 60:
        return warehouse_cache["rows"]
    warehouses = search_read_all(
        "stock.warehouse",
        ["|", ["name", "ilike", "Dark"], ["name", "ilike", "DS#"]],
        ["id", "name", "code", "lot_stock_id", "active"],
    )
    locations = search_read_all(
        "stock.location",
        [["usage", "=", "transit"]],
        ["id", "complete_name", "usage"],
    )
    rows: list[Warehouse] = []
    for row in warehouses:
        if row.get("active") is False:
            continue
        stock = row.get("lot_stock_id")
        name = str(row.get("name") or "")
        transit = next(
            (
                loc
                for loc in locations
                if name.lower() in str(loc.get("complete_name") or "").lower()
            ),
            None,
        )
        stock_id = m2o_id(stock) or 0
        if not stock_id:
            continue
        rows.append(
            Warehouse(
                id=int(row["id"]),
                name=name,
                code=str(row.get("code") or ""),
                stock_id=stock_id,
                stock_name=m2o_name(stock),
                transit_id=int(transit["id"]) if transit else None,
            )
        )
    warehouse_cache = {"at": datetime.now(UTC).timestamp(), "rows": rows}
    return rows


def store_tokens(warehouse: Warehouse) -> list[str]:
    return [
        token
        for token in norm(f"{warehouse.name} {warehouse.code}").split(" ")
        if len(token) >= 5 and token not in STOP and token not in PLACE_TOKENS
    ]


def match_stores(text: str, warehouses: list[Warehouse]) -> list[Warehouse]:
    hay = f" {norm(text)} "
    hits = []
    for warehouse in warehouses:
        code = norm(warehouse.code)
        if code and f" {code} " in hay:
            hits.append(warehouse)
            continue
        if any(token in hay for token in store_tokens(warehouse)):
            hits.append(warehouse)
    return hits


def parse_bucket(text: str) -> str | None:
    hay = f" {norm(text)} "
    if "rto in transit" in hay or "rto transit" in hay or "return in transit" in hay:
        return "RTO in transit"
    if "in transit" in hay or "transit" in hay:
        return "In transit"
    if "outgoing" in hay or "assign" in hay:
        return "Outgoing"
    if "deliver" in hay or "sale" in hay:
        return "Delivered"
    if "rto" in hay or "return" in hay or "wapas" in hay:
        return "RTO"
    if "adjust" in hay:
        return "Adjustment"
    if "cancel" in hay:
        return "Cancelled"
    if any(
        phrase in hay
        for phrase in (
            "hona chahiye",
            "on hand",
            "live stock",
            "free",
            "available",
            "pada",
            "stock",
        )
    ):
        return "On hand"
    if (
        re.search(r"\bin\b", hay)
        or "push" in hay
        or "receive" in hay
        or "receipt" in hay
        or "aaya" in hay
        or "aayi" in hay
    ):
        return "IN"
    if re.search(r"\bqty\b", hay) or "kitna" in hay or "kitni" in hay or "quantity" in hay:
        return "On hand"
    return None


def parse_mode(text: str) -> str:
    if re.search(r"\blist\b|\borders\b|\border\b|dikhao|konsi|kaun si", norm(text)):
        return "list"
    return "total"


def month_bounds(year: int, month: int) -> dict[str, str]:
    last = calendar.monthrange(year, month)[1]
    return {"from": f"{year}-{month:02d}-01", "to": f"{year}-{month:02d}-{last:02d}"}


def ist_now() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=330)


def parse_range(text: str) -> dict[str, str | None]:
    hay = norm(text)
    now = ist_now()
    this_year = now.year
    this_month = now.month
    if re.search(r"\b(this month|current month|is month|is mahine|yah month)\b", hay):
        return month_bounds(this_year, this_month)
    if re.search(
        r"\b(last month|previous month|pichla month|pichle month|pichla mahine|pichle mahine)\b",
        hay,
    ):
        month = 12 if this_month == 1 else this_month - 1
        year = this_year - 1 if this_month == 1 else this_year
        return month_bounds(year, month)
    numeric = re.search(r"\b(1[0-2]|0?[1-9])\s*[/-]\s*(20\d{2})\b", hay)
    if numeric:
        return month_bounds(int(numeric.group(2)), int(numeric.group(1)))
    year_match = re.search(r"\b(20\d{2})\b", hay)
    year = int(year_match.group(1)) if year_match else this_year
    month_name = next(
        (
            name
            for name in sorted(MONTHS, key=len, reverse=True)
            if re.search(rf"\b{name}\b", hay)
        ),
        None,
    )
    if not month_name:
        if year_match:
            return {"from": f"{year}-01-01", "to": f"{year}-12-31"}
        return {"from": None, "to": None}
    return month_bounds(year, MONTHS[month_name])


def product_words(text: str, warehouses: list[Warehouse]) -> list[str]:
    used = {token for warehouse in warehouses for token in store_tokens(warehouse)}
    return [
        word
        for word in norm(text).split(" ")
        if len(word) >= 3 and word not in STOP and word not in used and word not in MONTHS
    ]


def product_label(row: dict[str, Any]) -> str:
    name = str(row.get("display_name") or row.get("name") or "")
    sku = str(row.get("default_code") or "")
    attrs = row.get("product_template_attribute_value_ids")
    attr_text = ""
    if isinstance(attrs, list):
        attr_text = " ".join(label for item in attrs if (label := m2o_name(item)))
    base = f"{name} {attr_text}" if attr_text and attr_text.lower() not in name.lower() else name
    return f"{base} · {sku}" if sku else base


def search_products(words: list[str]) -> list[ProductRow]:
    from app.modules.webtechAIAgent.reconciliation.entity_normalization import (
        norm as fold,
    )
    from app.modules.webtechAIAgent.reconciliation.entity_normalization import (
        or_ilike,
        spelling_variants,
    )

    sku = next((word for word in words if re.fullmatch(r"\d{2,6}", word)), None)
    names = [word for word in words if not re.fullmatch(r"\d{2,6}", word)]
    needle = (sorted(names, key=len, reverse=True) or [sku])[0]
    if not needle:
        return []
    domain: list[Any] = (
        [["default_code", "=", sku]] if sku and not names else or_ilike("name", spelling_variants(needle))
    )
    fields = ["id", "default_code", "name", "display_name", "product_template_attribute_value_ids"]
    try:
        rows = search_read_all("product.product", domain, fields, "default_code asc")
    except RuntimeError:
        rows = search_read_all(
            "product.product",
            domain,
            ["id", "default_code", "name", "display_name"],
            "default_code asc",
        )
    extra = [word for word in names if word != needle]
    numbers = [word for word in words if re.fullmatch(r"\d{2,6}", word)]
    filtered = []
    for row in rows:
        hay = fold(
            f"{row.get('name') or ''} {row.get('display_name') or ''} "
            f"{row.get('default_code') or ''} {product_label(row)}"
        )
        if names and numbers and not all(number in hay for number in numbers):
            continue
        if all(word in hay for word in extra):
            filtered.append(row)
    return [
        ProductRow(
            id=int(row["id"]),
            name=str(row.get("name") or ""),
            sku=str(row.get("default_code") or ""),
            label=product_label(row),
        )
        for row in filtered[:12]
    ]


def match_candidate(text: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    hay = norm(text)
    if re.fullmatch(r"\d+", hay):
        at = int(hay) - 1
        if 0 <= at < len(candidates):
            return candidates[at]
    words = [word for word in hay.split(" ") if len(word) >= 2]
    hits = []
    for item in candidates:
        label = norm(f"{item.get('label') or ''} {item.get('sku') or ''}")
        if all(word in label for word in words):
            hits.append(item)
    return hits[0] if len(hits) == 1 else None


def sale_ref(move: dict[str, Any], picking: dict[str, Any] | None) -> str:
    origin = str((picking or {}).get("origin") or move.get("origin") or "")
    if origin.startswith("AGRI"):
        return origin.split(" ")[0]
    sale = m2o_name(move.get("sale_line_id"))
    if sale.startswith("AGRI"):
        return sale.split(" - ")[0].strip()
    return origin


def in_range(iso: str | None, start: str | None, end: str | None) -> bool:
    if not start and not end:
        return True
    if not iso:
        return False
    if start and iso < start:
        return False
    return not (end and iso > end)


def load_moves(warehouse: Warehouse, product_id: int | None) -> list[MoveRow]:
    location_ids = [item for item in (warehouse.stock_id, warehouse.transit_id) if item]
    domain: list[Any] = [
        "|",
        ["location_id", "in", location_ids],
        ["location_dest_id", "in", location_ids],
    ]
    if product_id:
        domain = ["&", ["product_id", "=", product_id], *domain]
    moves = search_read_all(
        "stock.move",
        domain,
        [
            "id",
            "product_id",
            "reference",
            "origin",
            "state",
            "date",
            "product_uom_qty",
            "quantity",
            "location_id",
            "location_dest_id",
            "picking_id",
            "sale_line_id",
            "origin_returned_move_id",
        ],
    )
    picking_ids = list(
        {pid for move in moves if (pid := m2o_id(move.get("picking_id")))}
    )
    pickings: dict[int, dict[str, Any]] = {}
    for start in range(0, len(picking_ids), 80):
        chunk = picking_ids[start : start + 80]
        for row in search_read_all(
            "stock.picking",
            [["id", "in", chunk]],
            ["id", "name", "origin", "state", "partner_id", "scheduled_date", "date_done", "return_id"],
        ):
            pickings[int(row["id"])] = row
    loc_ids = {warehouse.stock_id}
    for move in moves:
        src = m2o_id(move.get("location_id"))
        dest = m2o_id(move.get("location_dest_id"))
        if src:
            loc_ids.add(src)
        if dest:
            loc_ids.add(dest)
    locations = search_read_all(
        "stock.location",
        [["id", "in", list(loc_ids)]],
        ["id", "usage"],
    )
    usage = {int(row["id"]): str(row.get("usage") or "") for row in locations}
    result: list[MoveRow] = []
    for move in moves:
        picking = pickings.get(m2o_id(move.get("picking_id")) or 0)
        bucket = classify(move, picking, usage, warehouse.stock_id, warehouse.transit_id)
        if not bucket:
            continue
        if move.get("state") == "done":
            when = ist_date_key((picking or {}).get("date_done")) or ist_date_key(move.get("date"))
        else:
            when = ist_date_key((picking or {}).get("scheduled_date")) or ist_date_key(move.get("date"))
        result.append(
            MoveRow(
                when=when,
                doc=str((picking or {}).get("name") or move.get("reference") or f"MOVE/{move.get('id')}"),
                bucket=bucket,
                state=str(move.get("state") or ""),
                sale=sale_ref(move, picking),
                customer=partner_name((picking or {}).get("partner_id")),
                qty=qty_of(move),
                demand=float(move.get("product_uom_qty") or 0),
                source=m2o_name(move.get("location_id")),
                dest=m2o_name(move.get("location_dest_id")),
            )
        )
    return result


def transit_qty(warehouse: Warehouse, product_id: int) -> float:
    if not warehouse.transit_id:
        return 0
    quants = search_read_all(
        "stock.quant",
        [["product_id", "=", product_id], ["location_id", "=", warehouse.transit_id]],
        ["quantity"],
    )
    return sum(float(row.get("quantity") or 0) for row in quants)


def on_hand(warehouse: Warehouse, product_id: int) -> dict[str, float]:
    quants = search_read_all(
        "stock.quant",
        [["product_id", "=", product_id], ["location_id", "=", warehouse.stock_id]],
        ["quantity", "reserved_quantity"],
    )
    qty = 0.0
    reserved = 0.0
    for row in quants:
        qty += float(row.get("quantity") or 0)
        reserved += float(row.get("reserved_quantity") or 0)
    return {"qty": qty, "reserved": reserved}


def fmt(value: float) -> str:
    rounded = round(value * 100) / 100
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def answer_from_moves(
    warehouse: Warehouse,
    product: ProductRow | None,
    bucket: str,
    start: str | None,
    end: str | None,
    mode: str,
) -> dict[str, Any]:
    moves = load_moves(warehouse, product.id if product else None)
    ranged = [
        row
        for row in moves
        if bucket in {"In transit", "On hand"} or in_range(row.when, start, end)
    ]
    period = f"{format_in(start)} se {format_in(end)}" if start and end else "poora hisaab"
    who = product.label if product else "saare products"

    if bucket == "On hand":
        if not product:
            return {"reply": "On hand ke liye product ka naam ya SKU batao.", "rows": []}
        live = on_hand(warehouse, product.id)
        from app.modules.webtechAIAgent.reconciliation.answer_formatting import stock_card

        return {
            "reply": stock_card(
                location=warehouse.name,
                product_name=product.name,
                sku=product.sku,
                variant="",
                updated_at=None,
                snapshot=datetime.now(UTC).date(),
                on_hand=live["qty"],
                reserved=live["reserved"],
                incoming=0,
            ),
            "rows": [],
        }

    if bucket == "In transit":
        if not product:
            return {"reply": "In transit ke liye product batao.", "rows": []}
        sitting = transit_qty(warehouse, product.id)
        return {
            "reply": (
                f"{warehouse.name}\n{who}\nAbhi transit location me {fmt(sitting)} qty hai. "
                "Yeh store on-hand me shamil nahi hai."
            ),
            "rows": [],
        }

    if bucket == "Adjustment":
        inn = sum(row.qty for row in ranged if row.bucket == "Adjustment IN")
        out = sum(row.qty for row in ranged if row.bucket == "Adjustment OUT")
        return {
            "reply": (
                f"{warehouse.name}\n{who}\nAdjustment · {period}\n"
                f"IN {fmt(inn)}\nOUT {fmt(out)}\nNet {fmt(inn - out)}"
            ),
            "rows": [],
        }

    picked = [row for row in ranged if row.bucket == bucket]
    total = sum((row.demand if bucket == "Cancelled" else row.qty) for row in picked)
    head = (
        f"{warehouse.name}\n{who}\n{bucket} · {period}\nTotal {fmt(total)} · {len(picked)} documents"
    )
    if mode != "list":
        return {"reply": head, "rows": []}
    shown = sorted(picked, key=lambda row: row.when or "", reverse=True)[:40]
    rows = [
        {
            "date": format_in(row.when),
            "doc": row.doc,
            "sale": row.sale,
            "customer": row.customer,
            "qty": row.demand if bucket == "Cancelled" else row.qty,
        }
        for row in shown
    ]
    more = ""
    if len(picked) > len(rows):
        more = f"\nAur {len(picked) - len(rows)} documents hain. Product ya date aur chhota karo."
    return {"reply": f"{head}{more}", "rows": rows}


def list_choices(title: str, _rows: list[dict[str, str]]) -> str:
    return title


def _context(incoming: dict[str, Any] | None) -> dict[str, Any]:
    context = dict(incoming or {})
    candidates = context.get("candidates")
    context["candidates"] = list(candidates) if candidates else []
    return context


def ask_webtech_agent(message: str, incoming: dict[str, Any] | None = None) -> dict[str, Any]:
    text = str(message or "").strip()
    context = _context(incoming)
    if not text:
        return {
            "reply": "Store, product, aur IN / delivered / RTO likho.",
            "context": context,
            "rows": [],
        }

    chose_product = False
    if context.get("pending") == "product" and context["candidates"]:
        picked = match_candidate(text, context["candidates"])
        if picked:
            context["productId"] = picked["id"]
            context["pending"] = None
            context["candidates"] = []
            chose_product = True
        elif not parse_bucket(text) and len(product_words(text, [])) <= 3:
            return {
                "reply": list_choices("Ye pack size me se ek chuno.", context["candidates"]),
                "context": context,
                "rows": [],
            }
        else:
            context["pending"] = None
            context["productId"] = None
            context["candidates"] = []

    if context.get("pending") == "store":
        hits = match_stores(text, load_warehouses())
        if len(hits) == 1:
            context["storeId"] = hits[0].id
            context["pending"] = None
        elif len(hits) > 1:
            return {
                "reply": list_choices(
                    "Kaun sa dark store?",
                    [{"label": f"{row.name} ({row.code})"} for row in hits],
                ),
                "context": {
                    **context,
                    "candidates": [
                        {"id": row.id, "sku": row.code, "label": row.name} for row in hits
                    ],
                },
                "rows": [],
            }

    if context.get("pending") == "bucket":
        bucket = parse_bucket(text)
        if bucket:
            context["bucket"] = bucket
            context["pending"] = None

    bucket = parse_bucket(text)
    date_range = parse_range(text)
    mode = parse_mode(text)
    if bucket:
        context["bucket"] = bucket
    if date_range["from"]:
        context["from"] = date_range["from"]
        context["to"] = date_range["to"]
    if re.search(r"\blist\b|\borders\b|\border\b|dikhao", norm(text)):
        context["mode"] = mode

    warehouses = load_warehouses()
    store_hits = match_stores(text, warehouses)
    if len(store_hits) == 1:
        context["storeId"] = store_hits[0].id
    if len(store_hits) > 1:
        context["pending"] = "store"
        return {
            "reply": list_choices(
                "Kaun sa dark store?",
                [{"label": f"{row.name} ({row.code})"} for row in store_hits],
            ),
            "context": {
                **context,
                "candidates": [
                    {"id": row.id, "sku": row.code, "label": row.name} for row in store_hits
                ],
            },
            "rows": [],
        }

    words = product_words(text, warehouses)
    waiting_on_choice = context.get("pending") == "product" and context.get("candidates")
    if not chose_product and words and not waiting_on_choice:
        products = search_products(words)
        if len(products) == 1:
            context["productId"] = products[0].id
            context["candidates"] = []
        elif len(products) > 1:
            context["pending"] = "product"
            context["productId"] = None
            context["candidates"] = [
                {"id": row.id, "sku": row.sku, "label": row.label} for row in products
            ]
            return {
                "reply": list_choices(f"{products[0].name} ke {len(products)} hain.", context["candidates"]),
                "context": context,
                "rows": [],
            }

    if not context.get("storeId"):
        context["pending"] = "store"
        context["candidates"] = []
        return {
            "reply": "Kaun sa dark store? Naam likho.",
            "context": context,
            "rows": [],
        }
    if not context.get("bucket"):
        context["pending"] = "bucket"
        return {
            "reply": "Kya chahiye: IN, delivered, RTO, in transit, outgoing, ya live on hand?",
            "context": context,
            "rows": [],
        }
    if not context.get("productId") and context.get("bucket") not in PRODUCT_FREE_BUCKETS:
        context["pending"] = "product"
        return {"reply": "Kaun sa product? Naam ya SKU likho.", "context": context, "rows": []}

    warehouse = next((row for row in warehouses if row.id == context["storeId"]), None)
    if warehouse is None:
        return {
            "reply": "Dark store nahi mila. Naam dobara likho.",
            "context": {**context, "storeId": None, "pending": "store"},
            "rows": [],
        }

    product: ProductRow | None = None
    if context.get("productId"):
        rows = search_read_all(
            "product.product",
            [["id", "=", context["productId"]]],
            ["id", "default_code", "name", "display_name"],
        )
        if rows:
            product = ProductRow(
                id=int(rows[0]["id"]),
                name=str(rows[0].get("name") or ""),
                sku=str(rows[0].get("default_code") or ""),
                label=product_label(rows[0]),
            )

    result = answer_from_moves(
        warehouse,
        product,
        str(context["bucket"]),
        context.get("from"),
        context.get("to"),
        context.get("mode") or "total",
    )
    return {**result, "context": {**context, "pending": None, "candidates": []}}
