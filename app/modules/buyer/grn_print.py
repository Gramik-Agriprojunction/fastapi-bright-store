"""Goods Receipt Note print, matching the Odoo incoming picking PDF."""

from datetime import datetime, timedelta, timezone
from html import escape

from app.modules.buyer.repository import BuyerGrn, BuyerShipment

_IST = timezone(timedelta(hours=5, minutes=30))

# Gramik header from the Odoo Goods Receipt Note print.
_CIN = "U51909UP2021PTC147165"
_REGISTERED_ADDRESS = (
    "2nd Floor, 213, 209B & 209C, Cyber Heights,\n"
    "GOMTI NAGAR, Omaxe Heights, Vibhuti Khand,\n"
    "Lucknow, Uttar Pradesh - 226010\n"
    "India"
)
_MSME = "UDYAM-UP-50-0028897"
_SIGNATURE = "Digitally Signed by Gramik ™"

# hsn, unit price, cgst %, sgst %, igst %
_CROP_TAX = {
    "Paddy (PR-126)": ("10061090", 22.0, 2.5, 2.5, 0.0),
    "Tomato": ("07020000", 18.0, 2.5, 2.5, 0.0),
    "Chilli": ("07096090", 40.0, 2.5, 2.5, 0.0),
    "Potato": ("07019000", 16.0, 2.5, 2.5, 0.0),
}


def _fmt(value: float) -> str:
    return f"{value:,.2f}"


def _party(
    name: str,
    lines: list[str],
    *,
    pan: str = "",
    gstin: str = "",
    mobile: str = "",
) -> dict[str, object]:
    return {
        "name": name,
        "lines": lines,
        "pan": pan,
        "gstin": gstin,
        "mobile": mobile,
    }


def build_grn_print(grn: BuyerGrn, ship: BuyerShipment) -> dict[str, object]:
    hsn, price, cgst_rate, sgst_rate, igst_rate = _CROP_TAX.get(
        grn.crop, ("10061090", 22.0, 2.5, 2.5, 0.0)
    )
    qty = grn.received_kg
    taxable = round(qty * price, 2)
    cgst = round(taxable * cgst_rate / 100, 2)
    sgst = round(taxable * sgst_rate / 100, 2)
    igst = round(taxable * igst_rate / 100, 2)
    line_total = round(taxable + cgst + sgst + igst, 2)
    gst_rate = cgst_rate + sgst_rate + igst_rate
    line = {
        "s_no": 1,
        "name": f"{grn.crop} · {grn.grade}",
        "hsn": hsn,
        "qty": qty,
        "qty_label": _fmt(qty),
        "uom": "Kg",
        "price_unit": price,
        "price_label": _fmt(price),
        "taxable_amount": taxable,
        "taxable_label": _fmt(taxable),
        "gst_rate": f"{gst_rate:.1f}%",
        "cgst_rate": cgst_rate,
        "cgst_amount": cgst,
        "cgst_label": _fmt(cgst),
        "sgst_rate": sgst_rate,
        "sgst_amount": sgst,
        "sgst_label": _fmt(sgst),
        "igst_rate": igst_rate,
        "igst_amount": igst,
        "igst_label": _fmt(igst),
        "total": line_total,
        "total_label": _fmt(line_total),
    }
    summary = {
        "hsn": hsn,
        "taxable_amount": taxable,
        "taxable_label": _fmt(taxable),
        "cgst_rate": cgst_rate,
        "cgst_amount": cgst,
        "cgst_label": _fmt(cgst),
        "sgst_rate": sgst_rate,
        "sgst_amount": sgst,
        "sgst_label": _fmt(sgst),
        "igst_rate": igst_rate,
        "igst_amount": igst,
        "igst_label": _fmt(igst),
        "total_tax": round(cgst + sgst + igst, 2),
        "total_tax_label": _fmt(cgst + sgst + igst),
    }
    parties = {
        "from": _party(
            ship.route_from,
            ["Collection Centre", "Hardoi, Uttar Pradesh – 241001"],
            pan="AAVCA3256A",
        ),
        "to": _party(
            ship.buyer_name,
            [ship.buyer_site, "Lucknow, Uttar Pradesh – 226010"],
            mobile="+91 99186 31475",
        ),
        "shipping": _party(
            ship.buyer_site,
            [ship.route_to, "Lucknow, Uttar Pradesh – 226010"],
            mobile="+91 99186 31475",
        ),
    }
    document = {
        "title": "Goods Receipt Note",
        "company": {
            "cin": _CIN,
            "registered_address": _REGISTERED_ADDRESS,
        },
        "transaction": {
            "supply_type": "Incoming Receipt",
            "source_document": grn.po_number,
            "reference_no": grn.id,
            "place_of_supply": "Uttar Pradesh",
            "status": "Done",
            "document_type": "GRN",
            "date": "28-09-2026",
        },
        "parties": parties,
        "lines": [line],
        "shipping_charges": 0.0,
        "shipping_label": "₹ 0.00",
        "grand_total": line_total,
        "grand_total_label": f"₹ {_fmt(line_total)}",
        "hsn_summary": [summary],
        "hsn_totals": {
            "taxable_label": _fmt(taxable),
            "cgst_label": _fmt(cgst),
            "sgst_label": _fmt(sgst),
            "igst_label": _fmt(igst),
            "total_tax_label": _fmt(cgst + sgst + igst),
        },
        "footer": {
            "printed_on": datetime.now(_IST).strftime("%d-%m-%y %H:%M:%S"),
            "msme": _MSME,
            "signature": _SIGNATURE,
        },
    }
    document["html"] = render_grn_html(document)
    return document


def _party_html(title: str, party: dict[str, object]) -> str:
    lines = "".join(f"{escape(str(line))}<br/>" for line in party["lines"])  # type: ignore[index]
    extra = ""
    if party["gstin"]:
        extra += f"GSTIN: {escape(str(party['gstin']))}<br/>"
    if party["pan"]:
        extra += f"PAN: {escape(str(party['pan']))}<br/>"
    if party["mobile"]:
        extra += f"Mobile: {escape(str(party['mobile']))}"
    return (
        "<td class='info-col'>"
        f"<strong>{escape(title)}</strong><br/>"
        f"<strong>{escape(str(party['name']))}</strong><br/>"
        f"{lines}{extra}</td>"
    )


def render_grn_html(document: dict[str, object]) -> str:
    company = document["company"]
    txn = document["transaction"]
    parties = document["parties"]
    footer = document["footer"]
    lines = document["lines"]
    summary = document["hsn_summary"]
    totals = document["hsn_totals"]
    assert isinstance(company, dict)
    assert isinstance(txn, dict)
    assert isinstance(parties, dict)
    assert isinstance(footer, dict)
    assert isinstance(lines, list)
    assert isinstance(summary, list)
    assert isinstance(totals, dict)
    address = "<br/>".join(escape(part) for part in str(company["registered_address"]).split("\n"))
    body_rows = []
    for line in lines:
        assert isinstance(line, dict)
        body_rows.append(
            "<tr>"
            f"<td class='text-center'>{line['s_no']}</td>"
            f"<td>{escape(str(line['name']))}</td>"
            f"<td class='text-center'>{escape(str(line['hsn']))}</td>"
            f"<td class='text-center'>{line['qty_label']}<br/><small>({escape(str(line['uom']))})</small></td>"
            f"<td class='text-right'>{line['price_label']}</td>"
            f"<td class='text-right'>{line['taxable_label']}</td>"
            f"<td class='text-center'>{escape(str(line['gst_rate']))}</td>"
            f"<td class='text-right'>{line['cgst_label']}</td>"
            f"<td class='text-right'>{line['sgst_label']}</td>"
            f"<td class='text-right'>{line['igst_label']}</td>"
            f"<td class='text-right'><strong>{line['total_label']}</strong></td>"
            "</tr>"
        )
    hsn_rows = []
    for row in summary:
        assert isinstance(row, dict)
        hsn_rows.append(
            "<tr>"
            f"<td class='text-center'>{escape(str(row['hsn']))}</td>"
            f"<td class='text-right'>{row['taxable_label']}</td>"
            f"<td class='text-center'>{row['cgst_rate']}%</td>"
            f"<td class='text-right'>{row['cgst_label']}</td>"
            f"<td class='text-center'>{row['sgst_rate']}%</td>"
            f"<td class='text-right'>{row['sgst_label']}</td>"
            f"<td class='text-center'>{row['igst_rate']}%</td>"
            f"<td class='text-right'>{row['igst_label']}</td>"
            f"<td class='text-right'><strong>{row['total_tax_label']}</strong></td>"
            "</tr>"
        )
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  body {{ font-family: Arial, sans-serif; font-size: 11px; color: #000; margin: 0; }}
  table {{ width: 100%; border-collapse: collapse; }}
  .header td {{ border: none; vertical-align: top; padding: 4px; }}
  .title {{ font-size: 20px; font-weight: bold; text-align: center; }}
  .section {{ background: #e9ecef; font-weight: bold; border: 1px solid #000; border-bottom: none; padding: 4px 8px; margin-top: 8px; }}
  .info-col {{ border: 1px solid #000; padding: 6px; width: 33.33%; vertical-align: top; }}
  .gramik-table th, .gramik-table td {{ border: 1px solid #000; padding: 4px; vertical-align: middle; }}
  .gramik-table th {{ background: #f8f9fa; font-weight: bold; text-align: center; }}
  .text-right {{ text-align: right; }}
  .text-center {{ text-align: center; }}
  .total-row td {{ background: #f8f9fa; font-weight: bold; }}
  .footer td {{ border: 1px solid #000; padding: 10px; vertical-align: middle; }}
</style>
</head>
<body>
<table class="header">
  <tr>
    <td style="width:33%">
      <strong>CIN:</strong> {escape(str(company["cin"]))}
    </td>
    <td class="title" style="width:34%">{escape(str(document["title"]))}</td>
    <td style="width:33%; text-align:right">
      <strong>Registered Address:</strong><br/>{address}
    </td>
  </tr>
</table>
<div class="section">1.Transaction Details</div>
<table>
  <tr>
    <td class="info-col"><strong>Supply Type Code : </strong>{escape(str(txn["supply_type"]))}</td>
    <td class="info-col" style="text-align:right">
      <strong>Source Document : </strong>{escape(str(txn["source_document"]))}<br/>
      <strong>Reference No : </strong>{escape(str(txn["reference_no"]))}
    </td>
  </tr>
  <tr>
    <td class="info-col"><strong>Place of Supply : </strong>{escape(str(txn["place_of_supply"]))}</td>
    <td class="info-col" style="text-align:right"><strong>Status : </strong>{escape(str(txn["status"]))}</td>
  </tr>
  <tr>
    <td class="info-col"><strong>Document Type : </strong>{escape(str(txn["document_type"]))}</td>
    <td class="info-col" style="text-align:right"><strong>Date : </strong>{escape(str(txn["date"]))}</td>
  </tr>
</table>
<div class="section">2.Party Details</div>
<table>
  <tr>
    {_party_html("Location (From):", parties["from"])}
    {_party_html("Location (To):", parties["to"])}
    {_party_html("Shipping Address:", parties["shipping"])}
  </tr>
</table>
<div class="section">4.Details of Goods / Services</div>
<table class="gramik-table">
  <thead>
    <tr>
      <th rowspan="2">S.No.</th>
      <th rowspan="2">Item Description</th>
      <th rowspan="2">HSN / SAC Code</th>
      <th rowspan="2">Quantity (Unit)</th>
      <th rowspan="2">Unit Price (Rs)</th>
      <th rowspan="2">Taxable Amount(Rs)</th>
      <th rowspan="2">GST Rate</th>
      <th colspan="3">Tax Rate</th>
      <th rowspan="2">Total</th>
    </tr>
    <tr>
      <th>CGST</th>
      <th>SGST</th>
      <th>IGST</th>
    </tr>
  </thead>
  <tbody>
    {"".join(body_rows)}
    <tr>
      <td colspan="10" class="text-right"><strong>Shipping Charges :</strong></td>
      <td class="text-right"><strong>{document["shipping_label"]}</strong></td>
    </tr>
    <tr class="total-row">
      <td colspan="10" class="text-right">Grand Total :</td>
      <td class="text-right">{document["grand_total_label"]}</td>
    </tr>
  </tbody>
</table>
<div class="section">5. HSN/SAC Summary</div>
<table class="gramik-table">
  <thead>
    <tr>
      <th rowspan="2">HSN/SAC</th>
      <th rowspan="2">Taxable Amount</th>
      <th colspan="2">Central Tax</th>
      <th colspan="2">State Tax</th>
      <th colspan="2">Integrated Tax</th>
      <th rowspan="2">Total Tax Amount</th>
    </tr>
    <tr>
      <th>Rate</th><th>Amount</th>
      <th>Rate</th><th>Amount</th>
      <th>Rate</th><th>Amount</th>
    </tr>
  </thead>
  <tbody>
    {"".join(hsn_rows)}
    <tr class="total-row">
      <td>Total</td>
      <td class="text-right">{totals["taxable_label"]}</td>
      <td></td>
      <td class="text-right">{totals["cgst_label"]}</td>
      <td></td>
      <td class="text-right">{totals["sgst_label"]}</td>
      <td></td>
      <td class="text-right">{totals["igst_label"]}</td>
      <td class="text-right">{totals["total_tax_label"]}</td>
    </tr>
  </tbody>
</table>
<table class="footer" style="margin-top:16px">
  <tr>
    <td style="width:66%">
      <strong>Printed On :</strong> {escape(str(footer["printed_on"]))}<br/>
      <strong>MSME No :</strong> {escape(str(footer["msme"]))}
    </td>
    <td style="width:34%; text-align:center">
      <strong>{escape(str(footer["signature"]))}</strong>
    </td>
  </tr>
</table>
</body>
</html>
"""
