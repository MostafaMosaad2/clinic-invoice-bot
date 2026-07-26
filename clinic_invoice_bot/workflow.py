from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import parse_qs, urljoin, urlparse

from playwright.sync_api import Page

from .config import Settings
from .forms import absolutize, ask, choose_from_options


def login(page: Page, settings: Settings) -> None:
    page.goto(settings.login_url, wait_until="domcontentloaded")
    page.wait_for_selector("#username", timeout=30000)
    page.fill("#username", settings.username)
    page.fill("#password", settings.password)
    page.click("#submit")
    page.wait_for_load_state("domcontentloaded")

    if "login.php" in page.url and "err=" in page.url:
        raise RuntimeError(
            "Login failed: Invalid Entry Data. "
            "Check CLINIC_USERNAME / CLINIC_PASSWORD in .env."
        )

    page.goto(settings.home_url, wait_until="domcontentloaded")
    if "login.php" in page.url:
        raise RuntimeError("Login session was not established (redirected to login).")
    print(f"Logged in. Current page: {page.url}")


def patient_services_url_for(settings: Settings, st_id: str) -> str:
    return f"{settings.base_url.rstrip('/')}/patient_services_add.php?st_id={st_id}"


def search_patients_by_national_id(
    page: Page,
    settings: Settings,
    national_id: str,
) -> list[dict]:
    """
    Search IMDAD patient suggest API (process12.php) by national ID / SSN.
    Returns items like: {name, st_id, phone, label, national_id}
    """
    query = str(national_id or "").strip()
    if not query:
        raise RuntimeError("National ID is required.")

    endpoint = f"{settings.base_url.rstrip('/')}/process12.php"
    response = page.request.post(endpoint, form={"name12": query})
    html = response.text() or ""
    if not html.strip():
        return []

    raw_values = re.findall(r"fillSearch12\('([^']+)'\)", html)
    if not raw_values:
        # Fallback: plain list text Name*st_id*phone
        raw_values = re.findall(
            r"<li[^>]*>\s*([^<]+?)\s*</li>",
            html,
            flags=re.I,
        )

    results: list[dict] = []
    seen: set[str] = set()
    for raw in raw_values:
        label = re.sub(r"\s+", " ", raw).strip()
        parts = [p.strip() for p in label.split("*")]
        if len(parts) < 2 or not parts[1].isdigit():
            continue
        st_id = parts[1]
        if st_id in seen:
            continue
        seen.add(st_id)
        results.append(
            {
                "national_id": query,
                "name": parts[0],
                "st_id": st_id,
                "phone": parts[2] if len(parts) > 2 else "",
                "label": label,
                "patient_url": f"{settings.base_url.rstrip('/')}/stq_search2.php?id={st_id}",
                "patient_services_url": patient_services_url_for(settings, st_id),
            }
        )
    return results


def resolve_patient_by_national_id(
    page: Page,
    settings: Settings,
    national_id: str,
) -> dict:
    matches = search_patients_by_national_id(page, settings, national_id)
    if not matches:
        raise RuntimeError(f"No patient found for national ID: {national_id}")
    if len(matches) > 1:
        # Prefer exact file/phone packaging; take first stable match.
        print(f"Found {len(matches)} patients for {national_id}; using first match.")
    chosen = matches[0]
    print(
        f"Patient found: {chosen['name']} (st_id={chosen['st_id']}, phone={chosen.get('phone')})"
    )
    return chosen


def inspect_patient_services(page: Page, settings: Settings) -> None:
    page.goto(settings.patient_services_url, wait_until="domcontentloaded")
    if "login.php" in page.url:
        raise RuntimeError("Not logged in; cannot open patient services page.")

    clinics = _select_options(page, "select[name='clinic_id']")
    print("\nClinics:")
    for opt in clinics:
        print(f"  {opt['value']}: {opt['text']}")

    if clinics:
        first = next((c for c in clinics if c["value"]), None)
        if first:
            page.select_option("select[name='clinic_id']", first["value"])
            page.wait_for_selector("select[name='s_id']", timeout=10000)
            services = _select_options(page, "select[name='s_id']")
            print(f"\nServices for clinic {first['text']} ({len(services)}):")
            for opt in services[:40]:
                print(f"  {opt['value']}: {opt['text']}")
            if len(services) > 40:
                print(f"  ... and {len(services) - 40} more")

    print("\nPayment/date fields present:")
    for sel in (
        "input[name='cash_amount']",
        "input[name='net_amount']",
        "select[name='day8']",
        "select[name='month8']",
        "select[name='year8']",
        "input#submit",
    ):
        print(f"  {sel}: {page.locator(sel).count()}")


def create_invoice(
    page: Page,
    settings: Settings,
    *,
    clinic: str | None = None,
    service: str | None = None,
    amount: str | None = None,
    invoice_date: str | None = None,
    national_id: str | None = None,
    st_id: str | None = None,
) -> dict:
    """
    Create an invoice for the configured patient visit.

    Returns metadata for the created invoice (st_id/rec_id/serial/urls).
    Date is changed AFTER create via the patient invoices page — not here.
    """
    del invoice_date  # date is applied in change_invoice_date_from_patient()

    patient = None
    if national_id:
        patient = resolve_patient_by_national_id(page, settings, national_id)
        st_id = patient["st_id"]
    st_id = st_id or _st_id_from_url(settings.patient_services_url)
    if not st_id:
        raise RuntimeError("Patient st_id is required (provide national_id or PATIENT_SERVICES_URL).")

    services_url = patient_services_url_for(settings, st_id)
    before_ids = _list_invoice_ids(page, settings, st_id)

    page.goto(services_url, wait_until="domcontentloaded")
    if "login.php" in page.url:
        raise RuntimeError("Not logged in; cannot open patient services page.")

    st_id = st_id or _st_id_from_page(page)

    clinic_opts = _select_options(page, "select[name='clinic_id']")
    clinic_value = _resolve_option(clinic_opts, clinic, "Choose clinic")
    page.select_option("select[name='clinic_id']", clinic_value)
    page.wait_for_selector("select[name='s_id']", timeout=15000)
    page.wait_for_timeout(400)

    service_opts = _select_options(page, "select[name='s_id']")
    service_value = _resolve_option(service_opts, service, "Choose service")
    page.select_option("select[name='s_id']", service_value)
    # Keep search box in sync; some builds post s_name as well as s_id.
    service_label = page.locator("select[name='s_id'] option:checked").inner_text().strip()
    if page.locator("#SearchBox12").count():
        page.fill("#SearchBox12", service_label)

    before_service_marker = _service_line_count(page)
    _click_add_service(page)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)

    after_service_marker = _service_line_count(page)
    if after_service_marker <= before_service_marker and not _page_has_added_service(page, service_label):
        raise RuntimeError(
            "Clicked إضافة : Add but the service line did not appear. "
            "Check clinic/service selection and try again."
        )
    print(f"Service added via إضافة : Add ({service_label})")

    if page.locator("input[name='cash_amount']").count() == 0:
        raise RuntimeError("cash_amount field missing after adding the service.")

    paid = amount or ask("Amount paid (cash)")
    page.fill("input[name='cash_amount']", str(paid))
    # Credit card is also marked required in the UI; 0 is typically accepted for cash-only.
    if page.locator("input[name='net_amount']").count():
        current_net = page.input_value("input[name='net_amount']")
        if not (current_net or "").strip():
            page.fill("input[name='net_amount']", "0")

    # The finalize button calls get_rec() which is often undefined in this build.
    page.evaluate("() => { window.get_rec = window.get_rec || function () { return true; }; }")
    finalize = page.locator("input#submit[name='submit'], input[type='submit'][value*='Referral']")
    finalize.first.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)
    print(f"Finalize submitted. Current page: {page.url}")

    created = _find_new_invoice(page, settings, st_id, before_ids)
    if patient:
        created["patient_name"] = patient.get("name")
        created["national_id"] = patient.get("national_id")
        created["phone"] = patient.get("phone")
    print(
        "Created invoice: "
        f"rec_id={created.get('rec_id')} serial={created.get('serial')} "
        f"edit={created.get('edit_url')}"
    )
    return created


def change_invoice_date_from_patient(
    page: Page,
    settings: Settings,
    *,
    st_id: str,
    rec_id: str | None,
    serial: str | None,
    new_date: str,
) -> dict:
    """
    User-required flow:
    1) open patient page
    2) open/search patient invoices
    3) open that invoice edit page
    4) change date and save
    """
    if not st_id:
        raise RuntimeError("Missing patient st_id; cannot reopen patient invoices.")

    base = settings.base_url.rstrip("/")
    patient_url = f"{base}/stq_search2.php?id={st_id}"
    list_url = f"{base}/recs.php?sid={st_id}"

    print(f"Re-entering patient page: {patient_url}")
    page.goto(patient_url, wait_until="domcontentloaded")
    if "login.php" in page.url:
        raise RuntimeError("Session expired while opening patient page.")

    print(f"Opening patient invoices: {list_url}")
    page.goto(list_url, wait_until="domcontentloaded")

    if serial:
        _search_invoice_on_list(page, serial)

    edit_href = _find_edit_href(page, rec_id=rec_id, serial=serial)
    if not edit_href:
        raise RuntimeError(
            f"Could not find invoice edit link on patient invoices "
            f"(rec_id={rec_id}, serial={serial})."
        )

    edit_url = absolutize(base, edit_href) if not edit_href.startswith("http") else edit_href
    # Prefer clicking the on-page link (keeps referrer/session behavior).
    link = page.locator(f"a[href='{edit_href}']")
    if link.count():
        link.first.click()
    else:
        page.goto(edit_url, wait_until="domcontentloaded")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(800)

    if "login.php" in page.url:
        raise RuntimeError("Session expired while opening invoice edit.")
    if "alert.php" in page.url or "Forbidden" in (page.title() or ""):
        raise RuntimeError(
            "Invoice was created, but this username cannot open invoice edit "
            "(Forbidden Permission on rec_edit.php). "
            "Give this user permission to edit invoices / تغيير تاريخ الفاتورة, "
            "then run again."
        )

    if not _page_has_date_controls(page):
        raise RuntimeError(
            f"Opened invoice edit but no date fields were found. URL: {page.url}"
        )

    _set_day_month_year(page, new_date)
    _save_invoice_edit(page)
    print(f"Invoice date changed to {new_date}. Current page: {page.url}")
    return {
        "st_id": st_id,
        "rec_id": rec_id,
        "serial": serial,
        "edit_url": edit_url,
        "list_url": list_url,
        "date": new_date,
        "date_updated_on_edit": True,
    }


def update_invoice_date(
    page: Page,
    invoice_url: str,
    new_date: str,
    settings: Settings | None = None,
) -> bool:
    """Backward-compatible helper for CLI edit-date command."""
    parsed = urlparse(invoice_url)
    qs = parse_qs(parsed.query)
    st_id = (qs.get("sid") or qs.get("st_id") or [None])[0]
    rec_id = (qs.get("rec_id") or [None])[0]
    serial = (qs.get("serial_no") or qs.get("serial") or [None])[0]

    if not st_id and "recs.php" in invoice_url:
        page.goto(invoice_url, wait_until="domcontentloaded")
        href = _newest_edit_link(page)
        if not href:
            return False
        qs = parse_qs(urlparse(href).query)
        rec_id = (qs.get("rec_id") or [None])[0]
        serial = (qs.get("serial_no") or qs.get("serial") or [None])[0]
        st_id = _st_id_from_url(invoice_url)

    if not st_id:
        page.goto(invoice_url, wait_until="domcontentloaded")
        if "alert.php" in page.url or "Forbidden" in (page.title() or ""):
            raise RuntimeError(
                "Cannot edit invoice date: Forbidden Permission on edit page."
            )
        if not _page_has_date_controls(page):
            return False
        _set_day_month_year(page, new_date)
        _save_invoice_edit(page)
        return True

    if settings is None:
        raise RuntimeError("settings is required to reopen the patient invoices page.")

    change_invoice_date_from_patient(
        page,
        settings,
        st_id=st_id,
        rec_id=rec_id,
        serial=serial,
        new_date=new_date,
    )
    return True


def run_create_and_backdate(
    page: Page,
    settings: Settings,
    *,
    clinic: str | None = None,
    service: str | None = None,
    amount: str | None = None,
    invoice_date: str | None = None,
    national_id: str | None = None,
    st_id: str | None = None,
) -> dict:
    target_date = invoice_date or ask(
        "Invoice date (YYYY-MM-DD or DD/MM/YYYY)"
    )
    if not national_id and not st_id:
        national_id = ask("Patient national ID / SSN")
    created = create_invoice(
        page,
        settings,
        clinic=clinic,
        service=service,
        amount=amount,
        national_id=national_id,
        st_id=st_id,
    )

    print("Invoice created. Now re-entering patient page to change invoice date...")
    updated = change_invoice_date_from_patient(
        page,
        settings,
        st_id=created["st_id"],
        rec_id=created.get("rec_id"),
        serial=created.get("serial"),
        new_date=target_date,
    )
    print("Done: invoice created and date updated from patient invoices page.")
    return {
        **created,
        **updated,
        "invoice_url": created.get("edit_url") or created.get("list_url"),
        "date_updated_on_edit": True,
        "date": target_date,
    }


def _click_add_service(page: Page) -> None:
    """Click إضافة : Add. The button often exists in the DOM but is treated as not visible."""
    add = page.locator(
        'input[type="submit"][value*="إضافة"], '
        'input[type="submit"][value*="Add"]:not(#submit)'
    )
    if add.count() == 0:
        raise RuntimeError("Could not find إضافة : Add button on the invoice page.")

    try:
        add.first.scroll_into_view_if_needed(timeout=3000)
    except Exception:
        pass

    try:
        add.first.click(timeout=5000)
        return
    except Exception:
        pass

    # Fallback: force click, then native form submit for the clinic/service form.
    try:
        add.first.click(force=True, timeout=5000)
        return
    except Exception:
        pass

    submitted = page.evaluate(
        """() => {
          const clinic = document.querySelector("select[name='clinic_id']");
          const form = clinic && clinic.closest("form");
          if (!form) return false;
          const btn = Array.from(form.querySelectorAll('input[type="submit"]'))
            .find((el) => /إضافة|Add/.test(el.value || ""));
          if (btn && form.requestSubmit) {
            form.requestSubmit(btn);
            return true;
          }
          if (form.requestSubmit) {
            form.requestSubmit();
            return true;
          }
          form.submit();
          return true;
        }"""
    )
    if not submitted:
        raise RuntimeError("Failed to submit إضافة : Add form.")


def _service_line_count(page: Page) -> int:
    return page.evaluate(
        """() => {
          const deleteLinks = Array.from(document.querySelectorAll('a[href], input[type="submit"], button'))
            .filter((el) => /حذف|Delete|del|cancel/i.test((el.innerText || el.value || '') + (el.getAttribute('href') || '')));
          const rows = Array.from(document.querySelectorAll('table tr')).filter((tr) => {
            const t = (tr.innerText || '').trim();
            return t && !/الخدمة\\s*:\\s*Service|الكود\\s*:\\s*Code/.test(t) && /\\d/.test(t);
          });
          return Math.max(deleteLinks.length, rows.length);
        }"""
    )


def _page_has_added_service(page: Page, service_label: str) -> bool:
    body = page.locator("body").inner_text()
    if service_label and service_label in body:
        return True
    # Totals leave 0.00 when no services are present.
    return bool(re.search(r"الإجمالى\s*::\s*(?!0(?:\.0+)?\b)\d", body))


def select_options(page: Page, selector: str) -> list[dict[str, str]]:
    if page.locator(selector).count() == 0:
        return []
    return page.eval_on_selector_all(
        f"{selector} option",
        "els => els.map(o => ({value: String(o.value), text: (o.textContent || '').trim()}))",
    )


# Back-compat alias
_select_options = select_options


def _resolve_option(options: list[dict[str, str]], provided: str | None, prompt: str) -> str:
    usable = [o for o in options if str(o.get("value", "")).strip() not in {"", "0", "-1"}]
    if provided:
        for opt in usable:
            if provided == opt["value"] or provided.lower() == opt["text"].lower():
                return opt["value"]
            if provided.lower() in opt["text"].lower():
                return opt["value"]
        raise RuntimeError(f"Could not match {prompt.lower()} value: {provided!r}")
    return choose_from_options(usable, prompt + ":")


def _set_day_month_year(page: Page, raw_date: str) -> None:
    day, month, year = _parse_date_parts(raw_date)

    day_sel = _first_existing(
        page,
        ["select[name='day8']", "select#day", "select[name='day']"],
    )
    month_sel = _first_existing(
        page,
        ["select[name='month8']", "select#month", "select[name='month']"],
    )
    year_sel = _first_existing(
        page,
        ["select[name='year8']", "select#year", "select[name='year']"],
    )
    if not (day_sel and month_sel and year_sel):
        raise RuntimeError("Could not find day/month/year selects on the page.")

    page.select_option(day_sel, str(day))
    page.select_option(month_sel, str(month))
    page.select_option(year_sel, str(year))
    print(f"Set date selects to {year:04d}-{month:02d}-{day:02d}")


def _parse_date_parts(raw: str) -> tuple[int, int, int]:
    value = raw.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.day, dt.month, dt.year
        except ValueError:
            continue
    raise RuntimeError(
        f"Unrecognized date format: {raw!r}. Use YYYY-MM-DD or DD/MM/YYYY."
    )


def _first_existing(page: Page, selectors: list[str]) -> str | None:
    for sel in selectors:
        if page.locator(sel).count():
            return sel
    return None


def _st_id_from_url(url: str) -> str | None:
    qs = parse_qs(urlparse(url).query)
    vals = qs.get("st_id") or qs.get("sid") or qs.get("id")
    return vals[0] if vals else None


def _st_id_from_page(page: Page) -> str | None:
    if page.locator("input[name='st_id']").count():
        return page.input_value("input[name='st_id']")
    return _st_id_from_url(page.url)


def _list_invoice_ids(page: Page, settings: Settings, st_id: str | None) -> set[str]:
    if not st_id:
        return set()
    list_url = f"{settings.base_url.rstrip('/')}/recs.php?sid={st_id}"
    page.goto(list_url, wait_until="domcontentloaded")
    ids = page.evaluate(
        """() => Array.from(document.querySelectorAll('a[href*=\"rec_id=\"]'))
          .map(a => {
            const m = (a.getAttribute('href') || '').match(/rec_id=(\\d+)/);
            return m ? m[1] : null;
          })
          .filter(Boolean)"""
    )
    # return to add page caller will navigate again
    return set(ids)


def _find_new_invoice(
    page: Page,
    settings: Settings,
    st_id: str | None,
    before_ids: set[str],
) -> dict:
    list_url = f"{settings.base_url.rstrip('/')}/recs.php?sid={st_id}" if st_id else settings.base_url
    if not st_id:
        return {
            "st_id": st_id,
            "rec_id": None,
            "serial": None,
            "edit_url": None,
            "list_url": list_url,
        }

    page.goto(list_url, wait_until="domcontentloaded")
    invoices = page.evaluate(
        """() => Array.from(document.querySelectorAll('a[href*="rec_edit.php"]'))
          .map((a) => {
            const href = a.getAttribute('href') || '';
            const rec = (href.match(/rec_id=(\\d+)/) || [])[1] || null;
            const serial = (href.match(/serial_no=(\\d+)/) || href.match(/serial=(\\d+)/) || [])[1] || null;
            return {href, rec_id: rec, serial};
          })
          .filter((x) => x.rec_id)"""
    )

    ranked: list[tuple[int, dict]] = []
    for item in invoices:
        score = 2 if item["rec_id"] not in before_ids else 1
        score += int(item["rec_id"] or "0") / 1_000_000_000
        ranked.append((score, item))

    if not ranked:
        return {
            "st_id": st_id,
            "rec_id": None,
            "serial": None,
            "edit_url": None,
            "list_url": list_url,
        }

    ranked.sort(key=lambda item: item[0], reverse=True)
    best = ranked[0][1]
    edit_url = absolutize(settings.base_url, best["href"])
    return {
        "st_id": st_id,
        "rec_id": best.get("rec_id"),
        "serial": best.get("serial"),
        "edit_url": edit_url,
        "list_url": list_url,
    }


def _invoice_search_query(serial: str) -> str:
    """Clinic search expects invoice numbers with a G prefix (e.g. 136868 -> G136868)."""
    value = str(serial or "").strip()
    if not value:
        return value
    if value.upper().startswith("G"):
        return value
    return f"G{value}"


def _search_invoice_on_list(page: Page, serial: str) -> None:
    box = page.locator("#SearchBox12, input[name='search']")
    if box.count() == 0:
        return
    query = _invoice_search_query(serial)
    print(f"Searching invoices for: {query}")
    page.evaluate("() => { window.get_vno = window.get_vno || function () { return true; }; }")
    box.first.fill(query)
    form = page.locator("form").filter(has=page.locator("#SearchBox12, input[name='search']")).first
    submit = form.locator("button[type='submit'], input[type='submit']")
    try:
        with page.expect_navigation(timeout=10000):
            if submit.count():
                submit.first.click()
            else:
                box.first.press("Enter")
    except Exception:
        page.evaluate(
            """() => {
              const input = document.querySelector('#SearchBox12, input[name="search"]');
              const form = input && input.closest('form');
              if (!form) return;
              if (form.requestSubmit) form.requestSubmit();
              else HTMLFormElement.prototype.submit.call(form);
            }"""
        )
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(600)


def _find_edit_href(page: Page, *, rec_id: str | None, serial: str | None) -> str | None:
    hrefs = page.evaluate(
        """({recId, serial}) => {
          const links = Array.from(document.querySelectorAll('a[href*="rec_edit.php"]'))
            .map((a) => a.getAttribute('href') || '');
          if (recId) {
            const hit = links.find((h) => h.includes('rec_id=' + recId));
            if (hit) return hit;
          }
          if (serial) {
            const hit = links.find((h) => h.includes('serial_no=' + serial) || h.includes('serial=' + serial));
            if (hit) return hit;
          }
          // newest by rec_id
          return links.sort((a, b) => {
            const ra = Number((a.match(/rec_id=(\\d+)/) || [0,0])[1]);
            const rb = Number((b.match(/rec_id=(\\d+)/) || [0,0])[1]);
            return rb - ra;
          })[0] || null;
        }""",
        {"recId": rec_id, "serial": serial},
    )
    return hrefs


def _page_has_date_controls(page: Page) -> bool:
    selectors = [
        "select[name='day8']",
        "select[name='day']",
        "select#day",
        "select[name='month8']",
        "select[name='month']",
        "select#month",
        "select[name='year8']",
        "select[name='year']",
        "select#year",
        "input[name*='date' i]",
        "input[type='date']",
    ]
    return any(page.locator(sel).count() for sel in selectors)


def _save_invoice_edit(page: Page) -> None:
    page.evaluate("() => { window.get_rec = window.get_rec || function () { return true; }; }")
    candidates = [
        page.locator("input[type='submit'][value*='حفظ']"),
        page.locator("input[type='submit'][value*='Save']"),
        page.locator("input[type='submit'][value*='تعديل']"),
        page.locator("input[type='submit'][value*='Update']"),
        page.locator("button[type='submit']"),
        page.locator("input[type='submit'][name='submit']"),
        page.locator("input[type='submit']"),
    ]
    for cand in candidates:
        if cand.count():
            cand.first.click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(800)
            return
    raise RuntimeError("No save/submit button found on invoice edit page.")


def _newest_edit_link(page: Page) -> str | None:
    hrefs = page.evaluate(
        """() => Array.from(document.querySelectorAll('a[href*="rec_id="]'))
          .map(a => a.getAttribute('href') || '')
          .filter(h => /rec(?:k)?_edit\\.php/i.test(h))"""
    )
    if not hrefs:
        return None

    def rec_num(href: str) -> int:
        m = re.search(r"rec_id=(\d+)", href)
        return int(m.group(1)) if m else -1

    hrefs = sorted(hrefs, key=rec_num, reverse=True)
    return urljoin(page.url, hrefs[0])