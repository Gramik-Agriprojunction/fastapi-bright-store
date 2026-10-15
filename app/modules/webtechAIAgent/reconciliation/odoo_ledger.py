"""Build the same reconciliation ledger from live Odoo, for any warehouse and product."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo
from difflib import SequenceMatcher

from app.modules.webtechAIAgent.reconciliation.entity_normalization import (
    norm,
    or_ilike,
    search_terms,
    spelling_variants,
)
from app.modules.webtechAIAgent.reconciliation.workbook import Book, Move
from app.modules.webtechAIAgent.service import (
    Warehouse,
    load_moves,
    m2o_id,
    m2o_name,
    match_candidate,
    search_products,
    search_read_all,
)

IN_BUCKETS = {"IN", "RTO", "Adjustment IN"}
OUT_BUCKETS = {"Delivered", "Outgoing", "Adjustment OUT", "Other OUT"}
STOCK_CHANGE = {"IN", "RTO", "Adjustment IN", "Delivered", "Adjustment OUT", "Other OUT"}


def _warehouses_for(term: str) -> list[dict[str, object]]:
    clauses: list[object] = []
    for variant in spelling_variants(term):
        clauses.append(["name", "ilike", variant])
        clauses.append(["code", "ilike", variant])
    rows = search_read_all(
        "stock.warehouse",
        ["|"] * (len(clauses) - 1) + clauses,
        ["id", "name", "code", "lot_stock_id", "active"],
        "name asc",
    )
    found: list[dict[str, object]] = []
    seen: set[int] = set()
    for row in rows:
        if row.get("active") is False or not m2o_id(row.get("lot_stock_id")):
            continue
        hay = f" {norm(str(row.get('name') or ''))} {norm(str(row.get('code') or ''))} "
        if f" {term} " not in hay and term not in norm(str(row.get("code") or "")):
            continue
        warehouse_id = int(row["id"])
        if warehouse_id in seen:
            continue
        seen.add(warehouse_id)
        found.append(
            {
                "id": warehouse_id,
                "name": str(row.get("name") or ""),
                "code": str(row.get("code") or ""),
            }
        )
        if len(found) >= 8:
            break
    return found


def list_warehouses() -> list[dict[str, object]]:
    rows = search_read_all(
        "stock.warehouse",
        [["active", "=", True]],
        ["id", "name", "code", "lot_stock_id", "active"],
        "name asc",
        limit=30,
    )
    found: list[dict[str, object]] = []
    seen: set[int] = set()
    for row in rows:
        if row.get("active") is False or not m2o_id(row.get("lot_stock_id")):
            continue
        warehouse_id = int(row["id"])
        if warehouse_id in seen:
            continue
        seen.add(warehouse_id)
        found.append(
            {
                "id": warehouse_id,
                "name": str(row.get("name") or ""),
                "code": str(row.get("code") or ""),
            }
        )
    return found


def suggest_warehouses(words: list[str]) -> list[dict[str, object]]:
    rows = list_warehouses()
    if not words:
        return rows
    close = []
    for row in rows:
        hay = norm(f"{row['name']} {row['code']}")
        tokens = hay.split()
        if any(_close_word(word, hay, tokens) for word in words):
            close.append(row)
    return close or rows


def _warehouse_record(warehouse_id: int) -> Warehouse | None:
    rows = search_read_all(
        "stock.warehouse",
        [["id", "=", warehouse_id]],
        ["id", "name", "code", "lot_stock_id", "active"],
    )
    if not rows:
        return None
    row = rows[0]
    stock_id = m2o_id(row.get("lot_stock_id"))
    if not stock_id:
        return None
    name = str(row.get("name") or "")
    transit_rows = search_read_all(
        "stock.location",
        ["&", ["usage", "=", "transit"], ["complete_name", "ilike", name]],
        ["id", "complete_name"],
    )
    transit = next(
        (
            item
            for item in transit_rows
            if name.lower() in str(item.get("complete_name") or "").lower()
        ),
        None,
    )
    return Warehouse(
        id=int(row["id"]),
        name=name,
        code=str(row.get("code") or ""),
        stock_id=stock_id,
        stock_name=m2o_name(row.get("lot_stock_id")),
        transit_id=int(transit["id"]) if transit else None,
    )


def _as_ist(value: object) -> datetime | None:
    if not value or value is False:
        return None
    text = str(value).split(".")[0].replace("T", " ")
    try:
        parsed = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC).astimezone(ZoneInfo("Asia/Kolkata"))


def _quants(
    warehouse: Warehouse, product_id: int
) -> tuple[float | None, float | None, float | None, datetime | None]:
    rows = search_read_all(
        "stock.quant",
        [["product_id", "=", product_id], ["location_id", "=", warehouse.stock_id]],
        ["quantity", "reserved_quantity", "write_date", "in_date"],
    )
    if not rows:
        return 0.0, 0.0, 0.0, None
    on_hand = sum(float(row.get("quantity") or 0) for row in rows)
    reserved = sum(float(row.get("reserved_quantity") or 0) for row in rows)
    latest = None
    for row in rows:
        stamp = _as_ist(row.get("write_date")) or _as_ist(row.get("in_date"))
        if stamp is not None and (latest is None or stamp > latest):
            latest = stamp
    return on_hand, reserved, on_hand - reserved, latest


def _variant_name(product_id: int) -> str:
    try:
        rows = search_read_all(
            "product.product",
            [["id", "=", product_id]],
            ["name", "product_template_attribute_value_ids"],
        )
    except RuntimeError:
        return ""
    if not rows:
        return ""
    attrs = rows[0].get("product_template_attribute_value_ids")
    names: list[str] = []
    if isinstance(attrs, list):
        for item in attrs:
            label = m2o_name(item)
            if label:
                names.append(label)
    return " ".join(names)


def _incoming_qty(warehouse: Warehouse, product_id: int) -> float:
    try:
        rows = search_read_all(
            "stock.move",
            [
                "&",
                "&",
                ["product_id", "=", product_id],
                ["location_dest_id", "=", warehouse.stock_id],
                ["state", "in", ["assigned", "confirmed", "waiting", "partially_available"]],
            ],
            ["product_uom_qty"],
        )
    except RuntimeError:
        return 0.0
    return sum(float(row.get("product_uom_qty") or 0) for row in rows)


def _transit_qty(warehouse: Warehouse, product_id: int) -> float | None:
    if not warehouse.transit_id:
        return None
    rows = search_read_all(
        "stock.quant",
        [["product_id", "=", product_id], ["location_id", "=", warehouse.transit_id]],
        ["quantity"],
    )
    if not rows:
        return 0.0
    return sum(float(row.get("quantity") or 0) for row in rows)


def _apply_running(moves: list[Move]) -> None:
    running = 0.0
    for row in moves:
        changed = False
        if row.bucket in IN_BUCKETS and row.qty_in is not None:
            running += row.qty_in
            changed = True
        if row.bucket in {"Delivered", "Adjustment OUT", "Other OUT"} and row.qty_out is not None:
            running -= row.qty_out
            changed = True
        row.running = running if changed or row.bucket in STOCK_CHANGE else None


def build_book(warehouse_id: int, product: dict[str, object], today: date) -> Book | str:
    warehouse = _warehouse_record(warehouse_id)
    if warehouse is None:
        return "Warehouse nahi mila."
    product_id = int(product["id"])
    raw_rows = load_moves(warehouse, product_id)
    moves: list[Move] = []
    for row in raw_rows:
        if not row.when:
            continue
        when = datetime.fromisoformat(row.when)
        qty_in = row.qty if row.bucket in IN_BUCKETS else None
        qty_out = row.qty if row.bucket in OUT_BUCKETS else None
        moves.append(
            Move(
                when=when,
                doc=row.doc,
                bucket=row.bucket,
                state=row.state,
                sale=row.sale,
                partner=row.customer,
                source=row.source or warehouse.stock_name,
                dest=row.dest,
                qty_in=qty_in,
                qty_out=qty_out,
                running=None,
                return_of="",
                lot="",
                note="",
                demand=row.demand if row.bucket == "Cancelled" else None,
            )
        )
    moves.sort(key=lambda item: item.when)
    _apply_running(moves)
    on_hand, reserved, free, updated_at = _quants(warehouse, product_id)
    return Book(
        path="odoo",
        product_name=str(product.get("name") or ""),
        sku=str(product.get("sku") or ""),
        lot="",
        store_name=warehouse.name,
        warehouse=warehouse.name,
        location=warehouse.stock_name or warehouse.code,
        snapshot=today,
        company="",
        quant_id="",
        live_on_hand=on_hand,
        live_reserved=reserved,
        live_free=free,
        transit_on_hand=_transit_qty(warehouse, product_id),
        variant=_variant_name(product_id),
        stock_updated_at=updated_at,
        incoming_qty=_incoming_qty(warehouse, product_id),
        moves=moves,
    )


def _close_word(word: str, hay: str, tokens: list[str]) -> bool:
    if word in hay:
        return True
    if word.isdigit():
        return False
    return any(SequenceMatcher(None, word, token).ratio() >= 0.75 for token in tokens)


def suggest_products(words: list[str]) -> list:
    """Products whose name is close when the exact spelling missed."""
    from app.modules.webtechAIAgent.service import ProductRow, product_label

    needles: list[str] = []
    for word in words:
        if word.isdigit() and 2 <= len(word) <= 6:
            needles.append(word)
        elif len(word) >= 4:
            needles.extend((word[:4], word))
        elif len(word) >= 3:
            needles.append(word)
    unique = list(dict.fromkeys(needles))
    if not unique:
        return []
    try:
        rows = search_read_all(
            "product.product",
            or_ilike("name", unique),
            ["id", "default_code", "name", "display_name", "product_template_attribute_value_ids"],
            "default_code asc",
            limit=40,
        )
    except RuntimeError:
        rows = search_read_all(
            "product.product",
            or_ilike("name", unique),
            ["id", "default_code", "name", "display_name"],
            "default_code asc",
            limit=40,
        )
    ranked: list[tuple[float, ProductRow]] = []
    partials: list[tuple[float, ProductRow]] = []
    seen: set[int] = set()
    numbers = [word for word in words if word.isdigit()]
    names = [word for word in words if not word.isdigit()]
    for row in rows:
        product_id = int(row["id"])
        if product_id in seen:
            continue
        hay = norm(
            f"{row.get('name') or ''} {row.get('display_name') or ''} {row.get('default_code') or ''}"
        )
        tokens = hay.split()
        if numbers and not all(number in hay for number in numbers):
            continue
        word_scores = [
            max((SequenceMatcher(None, word, token).ratio() for token in tokens), default=0.0)
            for word in names
        ]
        partial_score = max(word_scores) if word_scores else 0.0
        product = ProductRow(
            id=product_id,
            name=str(row.get("name") or ""),
            sku=str(row.get("default_code") or ""),
            label=product_label(row),
        )
        close_name = bool(names) and all(_close_word(word, hay, tokens) for word in names)
        if close_name or (not names and numbers):
            score = sum(3.0 if word in hay else 1.0 for word in words)
            ranked.append((score, product))
        elif partial_score >= 0.5:
            partials.append((partial_score, product))
        seen.add(product_id)
    ranked.sort(key=lambda item: (-item[0], item[1].sku, item[1].id))
    if ranked:
        return [row for _score, row in ranked[:8]]
    partials = [item for item in partials if item[0] >= 0.5]
    partials.sort(key=lambda item: (-item[0], item[1].sku, item[1].id))
    return [row for _score, row in partials[:8]]


def _warehouse_prompt(rows: list[dict[str, object]]) -> str:
    if rows:
        return "Kaun sa warehouse? Naam Select Karo."
    return "Kaun sa warehouse? Naam likho."


def _ask_for_warehouse(
    updated: dict[str, object],
    words: list[str],
) -> tuple[dict[str, object], str]:
    rows = suggest_warehouses(words)
    updated["pending"] = "warehouse" if rows else None
    updated["candidates"] = [
        {"id": row["id"], "sku": row["code"], "label": f"{row['name']} ({row['code']})"}
        for row in rows
    ]
    return updated, _warehouse_prompt(updated["candidates"])


def resolve(
    text: str,
    context: dict[str, object],
    *,
    require_product: bool = True,
) -> tuple[dict[str, object], str | None]:
    """Attach Odoo warehouse and product ids. A string reply means ask the user again."""
    updated = dict(context)
    updated["warehouses"] = list(context.get("warehouses") or [])
    pending = str(context.get("pending") or "")
    candidates = list(context.get("candidates") or [])
    terms = search_terms(text)

    if pending and candidates:
        picked = match_candidate(text, candidates)
        if picked is None and not terms:
            if pending == "warehouse":
                return updated, _warehouse_prompt(candidates)
            return updated, "Kaun sa product?"
        if picked is not None:
            if pending == "warehouse":
                updated["warehouses"] = [
                    {"id": picked["id"], "name": picked.get("label") or "", "code": picked.get("sku") or ""}
                ]
            else:
                updated["product"] = {
                    "id": picked["id"],
                    "name": str(picked.get("label") or ""),
                    "sku": str(picked.get("sku") or ""),
                }
            updated["pending"] = None
            updated["candidates"] = []
            terms = []

    grouped = [(term, _warehouses_for(term)) for term in terms]
    grouped = [(term, hits) for term, hits in grouped if hits]
    warehouses: list[dict[str, object]] = []
    used: set[str] = set()
    ambiguous: tuple[str, list[dict[str, object]]] | None = None
    unique = [(term, hits[0]) for term, hits in grouped if len(hits) == 1]
    if unique:
        seen_ids: set[int] = set()
        for _term, row in unique:
            if int(row["id"]) in seen_ids:
                continue
            seen_ids.add(int(row["id"]))
            warehouses.append(row)
        for term, hits in grouped:
            hit_ids = {int(row["id"]) for row in hits}
            if hit_ids & seen_ids:
                used.add(term)
    elif grouped:
        narrowed = list(grouped[0][1])
        for _term, hits in grouped[1:]:
            ids = {int(row["id"]) for row in hits}
            narrowed = [row for row in narrowed if int(row["id"]) in ids]
        if len(narrowed) == 1:
            warehouses = narrowed
            used = {term for term, _hits in grouped}
        else:
            label, smallest = min(grouped, key=lambda item: len(item[1]))
            ambiguous = (label if not narrowed else grouped[0][0], narrowed or smallest)
    if ambiguous:
        term, hits = ambiguous
        updated["pending"] = "warehouse"
        updated["candidates"] = [
            {"id": row["id"], "sku": row["code"], "label": f"{row['name']} ({row['code']})"}
            for row in hits
        ]
        return updated, f"'{term}' par kai warehouse mile. Naam Select Karo."
    if warehouses:
        deduped: list[dict[str, object]] = []
        seen: set[int] = set()
        for row in warehouses:
            if int(row["id"]) in seen:
                continue
            seen.add(int(row["id"]))
            deduped.append(row)
        updated["warehouses"] = deduped
        updated["pending"] = None

    product_terms = [term for term in terms if term not in used]
    if product_terms and not require_product:
        product_terms = []
    if product_terms:
        products = search_products(product_terms)
        if len(products) == 1:
            updated["product"] = {
                "id": products[0].id,
                "name": products[0].name,
                "sku": products[0].sku,
            }
            updated["pending"] = None
        elif len(products) > 1:
            updated["pending"] = "product"
            updated["candidates"] = [
                {"id": row.id, "sku": row.sku, "label": row.label} for row in products
            ]
            return updated, f"{products[0].name} ke {len(products)} pack mile."
        else:
            suggestions = suggest_products(product_terms)
            if suggestions:
                updated["product"] = None
                updated["pending"] = "product"
                updated["candidates"] = [
                    {"id": row.id, "sku": row.sku, "label": row.label} for row in suggestions
                ]
                asked = " ".join(product_terms)
                return updated, f"'{asked}' exact naam nahi mila. Kya inme se koi hai?"
            if not updated.get("product") and updated.get("warehouses"):
                return updated, (
                    f"Product nahi mila: {' '.join(product_terms)}. "
                    "Naam ya SKU dobara likho."
                )

    if not updated.get("warehouses"):
        return _ask_for_warehouse(updated, [term for term in terms if term not in used])
    if not require_product:
        updated["candidates"] = []
        updated["pending"] = None
        return updated, None
    if not updated.get("product"):
        return updated, "Kaun sa product? Naam ya SKU likho."
    updated["candidates"] = []
    return updated, None
