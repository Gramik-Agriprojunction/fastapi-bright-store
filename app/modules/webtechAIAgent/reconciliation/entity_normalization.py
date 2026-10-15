"""Pull warehouse and product words out of a question. Odoo decides if they exist."""

from __future__ import annotations

import re

SKIP = {
    "kitna", "kitni", "kitne", "kitane", "hua", "hue", "hai", "hain", "hoga", "mein", "me", "mai", "main",
    "dark", "store", "warehouse", "darkstore", "month", "mahine", "order", "orders",
    "list", "qty", "quantity", "aur", "and", "the", "how", "much", "what", "ka",
    "ki", "ke", "se", "pe", "par", "do", "dena", "bhejo", "batao", "bata", "of",
    "for", "in", "on", "to", "from", "a", "an", "ya", "yaa", "please", "total",
    "successful", "sale", "sales", "push", "receive", "received", "aaya", "aayi", "aaye",
    "delivered", "delivery", "deliver", "rto", "transit", "outgoing", "this", "is",
    "was", "were", "with", "sheet", "hona", "chahiye", "live", "hand", "stock",
    "product", "products", "name", "wala", "wali", "wale", "kaun", "konsa", "which",
    "show", "dikhao", "nikalo", "current", "available", "free", "reserved", "cancel",
    "cancelled", "expected", "physical", "mismatch", "variance", "gap", "report",
    "summary", "status", "inward", "incoming", "outward", "lmd", "picking", "picked",
    "abhi", "aaj", "kal", "today", "yesterday", "bika", "bikri", "becha", "wapas",
    "wapis", "return", "assigned", "assign", "hisab", "hisaab", "poora", "poori", "pura", "puri", "sab",
    "all", "detail", "documents", "between", "zyada", "sabse", "dono", "pehla", "dusra",
    "excel", "xlsx", "workbook", "reconciliation", "reconcile", "reconcil",
    "saare", "sare", "sara", "sabhi", "kuch", "back", "banao", "banado", "bana", "file", "download", "export",
    "mail", "email", "bhej", "send", "karo", "kar", "attached", "attachment",
    "tak", "transfer", "transfers", "count", "number", "numbers", "wise", "sum", "ab", "abhi", "dc", "challan", "numberwise",
    "pure", "ledger", "ledgar", "leger", "chahiye", "chahie", "chaiye", "details", "format", "previous",
    "jaise", "jane", "jaane", "uski", "uska", "unki", "unka", "unke", "mujhe", "isko", "iski", "iske",
    "date", "dates", "field", "fields", "column", "columns", "document", "receipt", "chuke", "chuka",
    "chuki", "same", "bani", "thi", "out", "sku", "code", "bhi", "koi", "mang", "sakta", "hoon",
    "productwise", "kya", "report", "nikalo", "nikaalo",
}


def norm(value: str) -> str:
    text = value.lower().replace("lavkhush", "lavkush").replace("luvkush", "lavkush")
    text = re.sub(r"\b(mustard|mustered|musterd|muster)\b", "musturd", text)
    text = re.sub(r"\bram\s+nagar\b", "ramnagar", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def spelling_variants(term: str) -> list[str]:
    """Odoo stores some names with a different spelling than the question."""
    groups = (
        ("lavkush", "lavkhush", "luvkush"),
        ("musturd", "mustard", "musterd", "mustered", "muster"),
    )
    for group in groups:
        if term in group:
            return list(group)
    return [term]


def or_ilike(field: str, terms: list[str]) -> list[object]:
    clauses: list[object] = [[field, "ilike", term] for term in terms]
    if len(clauses) == 1:
        return clauses
    return ["|"] * (len(clauses) - 1) + clauses


def search_terms(text: str) -> list[str]:
    from app.modules.webtechAIAgent.reconciliation.question_understanding import MONTHS

    cleaned = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", " ", text or "")
    terms: list[str] = []
    for word in norm(cleaned).split():
        if word in SKIP or word in MONTHS:
            continue
        if re.fullmatch(r"20\d{2}", word):
            continue
        if re.fullmatch(r"\d{2,6}", word) or len(word) >= 3:
            terms.append(word)
    return terms
