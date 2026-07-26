"""Helpers for discovering and filling clinic form fields."""

from __future__ import annotations

import re
from typing import Any

from playwright.sync_api import Locator, Page


CLINIC_HINTS = (
    "clinic",
    "clinics",
    "clinc",
    "branch",
    "dept",
    "department",
    "قسم",
    "عيادة",
    "العيادة",
    "فرع",
    "clinic_id",
    "cl_id",
    "dep_id",
    "department_id",
)

SERVICE_HINTS = (
    "service",
    "services",
    "serv",
    "خدمة",
    "الخدمات",
    "الخدمة",
    "service_id",
    "ser_id",
    "serv_id",
    "item",
)

PAID_HINTS = (
    "paid",
    "pay",
    "payment",
    "amount_paid",
    "cash",
    "received",
    "مدفوع",
    "المدفوع",
    "دفعة",
    "المبلغ",
    "قيمة",
    "amount",
    "price",
    "total",
    "net",
)

DATE_HINTS = (
    "date",
    "invoice_date",
    "bill_date",
    "service_date",
    "trans_date",
    "تاريخ",
    "date_add",
    "add_date",
    "dt",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _score_field(meta: dict[str, str], hints: tuple[str, ...]) -> int:
    blob = " ".join(
        [
            meta.get("name", ""),
            meta.get("id", ""),
            meta.get("placeholder", ""),
            meta.get("label", ""),
            meta.get("nearby", ""),
        ]
    )
    blob = _norm(blob)
    score = 0
    for hint in hints:
        h = hint.lower()
        if blob == h:
            score += 100
        elif h in blob:
            score += 20 + min(len(h), 20)
    return score


def collect_fields(page: Page) -> list[dict[str, Any]]:
    return page.evaluate(
        """() => {
          const nearText = (el) => {
            const parts = [];
            const label = el.closest('label') || (el.id && document.querySelector(`label[for="${el.id}"]`));
            if (label) parts.push(label.innerText || '');
            const td = el.closest('td, th, div, span, li');
            if (td) {
              const prev = td.previousElementSibling;
              if (prev) parts.push(prev.innerText || '');
              parts.push((td.innerText || '').slice(0, 120));
            }
            return parts.join(' ').replace(/\\s+/g, ' ').trim();
          };

          const nodes = Array.from(document.querySelectorAll('input, select, textarea'));
          return nodes.map((el, index) => {
            const tag = el.tagName.toLowerCase();
            const type = (el.getAttribute('type') || (tag === 'select' ? 'select' : tag)).toLowerCase();
            const options = tag === 'select'
              ? Array.from(el.options).map(o => ({value: o.value, text: (o.text || '').trim()}))
              : [];
            return {
              index,
              tag,
              type,
              name: el.name || '',
              id: el.id || '',
              placeholder: el.placeholder || '',
              value: el.value || '',
              label: '',
              nearby: nearText(el),
              options,
            };
          });
        }"""
    )


def best_field(fields: list[dict[str, Any]], hints: tuple[str, ...], types: set[str] | None = None) -> dict[str, Any] | None:
    scored: list[tuple[int, dict[str, Any]]] = []
    for field in fields:
        if types and field.get("type") not in types and field.get("tag") not in types:
            continue
        score = _score_field(field, hints)
        if score > 0:
            scored.append((score, field))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def locator_for(page: Page, field: dict[str, Any]) -> Locator:
    if field.get("id"):
        return page.locator(f"#{field['id']}")
    if field.get("name"):
        return page.locator(f"[name=\"{field['name']}\"]").first
    raise ValueError(f"Field has no id/name: {field}")


def print_fields(fields: list[dict[str, Any]]) -> None:
    print("\nDetected form fields:")
    for field in fields:
        opts = field.get("options") or []
        opt_preview = ""
        if opts:
            sample = ", ".join(f"{o['value']}:{o['text']}" for o in opts[:5])
            opt_preview = f" options[{len(opts)}]=[{sample}{'...' if len(opts) > 5 else ''}]"
        print(
            f"  [{field['index']}] <{field['tag']} type={field['type']}> "
            f"name={field['name']!r} id={field['id']!r} nearby={field['nearby'][:80]!r}{opt_preview}"
        )


def choose_from_options(options: list[dict[str, str]], prompt: str) -> str:
    usable = [o for o in options if str(o.get("value", "")).strip() not in {"", "0", "-1"}]
    if not usable:
        usable = options

    print(f"\n{prompt}")
    for i, opt in enumerate(usable, start=1):
        print(f"  {i}. {opt.get('text') or opt.get('value')}  (value={opt.get('value')})")

    while True:
        raw = input("Enter number or exact value/text: ").strip()
        if not raw:
            continue
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(usable):
                return str(usable[idx - 1]["value"])
        for opt in usable:
            if raw == str(opt.get("value")) or _norm(raw) == _norm(opt.get("text", "")):
                return str(opt["value"])
        print("Invalid choice, try again.")


def select_value(page: Page, field: dict[str, Any], value: str) -> None:
    loc = locator_for(page, field)
    loc.select_option(value)


def fill_text(page: Page, field: dict[str, Any], value: str) -> None:
    loc = locator_for(page, field)
    loc.fill("")
    loc.fill(str(value))


def set_date_value(page: Page, field: dict[str, Any], value: str) -> None:
    loc = locator_for(page, field)
    tag = field.get("tag")
    ftype = field.get("type")
    if tag == "select":
        # try exact value, then text match
        try:
            loc.select_option(value)
            return
        except Exception:
            loc.select_option(label=value)
            return
    # Prefer setting value via JS for date pickers that ignore fill()
    page.evaluate(
        """({selector, value}) => {
          const el = document.querySelector(selector);
          if (!el) return;
          el.focus();
          el.value = value;
          el.dispatchEvent(new Event('input', {bubbles: true}));
          el.dispatchEvent(new Event('change', {bubbles: true}));
        }""",
        {
            "selector": f"#{field['id']}" if field.get("id") else f"[name=\"{field['name']}\"]",
            "value": value,
        },
    )
    if ftype in {"date", "text", "tel"} or tag == "input":
        try:
            loc.fill(value)
        except Exception:
            pass


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default


def find_submit(page: Page) -> Locator:
    candidates = [
        page.locator("input[type='submit']"),
        page.locator("button[type='submit']"),
        page.get_by_role("button", name=re.compile(r"save|add|submit|حفظ|اضافة|إضافة|تسجيل", re.I)),
        page.locator("input[type='button'][value*='حفظ'], input[type='button'][value*='Save']"),
    ]
    for cand in candidates:
        if cand.count() > 0:
            return cand.first
    raise RuntimeError("Could not find a submit/save button on the page.")


def extract_invoice_links(page: Page) -> list[dict[str, str]]:
    return page.evaluate(
        """() => {
          const links = Array.from(document.querySelectorAll('a[href]'));
          const out = [];
          for (const a of links) {
            const href = a.getAttribute('href') || '';
            if (/patient_services|invoice|bill|service/i.test(href) && /(edit|view|update|id=|ps_id=|inv=)/i.test(href)) {
              out.push({href, text: (a.innerText || '').trim().slice(0, 80)});
            }
          }
          return out;
        }"""
    )


def absolutize(base_url: str, href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    base = base_url.rstrip("/")
    if href.startswith("/"):
        # keep host from base
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(base_url)
        return urlunsplit((parts.scheme, parts.netloc, href, "", ""))
    return f"{base}/{href.lstrip('./')}"