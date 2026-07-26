from __future__ import annotations

import threading
from typing import Any
from urllib.parse import parse_qs, urlparse

from .browser import open_browser
from .config import Settings, load_settings
from .workflow import login, run_create_and_backdate, search_patients_by_national_id, select_options

_lock = threading.Lock()


def get_settings(*, headed: bool | None = None) -> Settings:
    settings = load_settings()
    if headed is None:
        return settings
    return Settings(
        base_url=settings.base_url,
        username=settings.username,
        password=settings.password,
        patient_services_url=settings.patient_services_url,
        headed=headed,
        slow_mo_ms=settings.slow_mo_ms,
    )


def patient_meta(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    qs = parse_qs(urlparse(settings.patient_services_url).query)
    st_id = (qs.get("st_id") or [""])[0]
    return {
        "base_url": settings.base_url,
        "patient_services_url": settings.patient_services_url,
        "st_id": st_id,
        "username": settings.username,
    }


def fetch_clinics(*, headed: bool = False) -> list[dict[str, str]]:
    settings = get_settings(headed=headed)
    with _lock:
        with open_browser(settings) as (_pw, _browser, page):
            login(page, settings)
            page.goto(settings.patient_services_url, wait_until="domcontentloaded")
            options = select_options(page, "select[name='clinic_id']")
            return [o for o in options if str(o.get("value", "")).strip() not in {"", "0", "-1"}]


def fetch_services(clinic_id: str, *, headed: bool = False) -> list[dict[str, str]]:
    if not clinic_id:
        raise ValueError("clinic_id is required")
    settings = get_settings(headed=headed)
    with _lock:
        with open_browser(settings) as (_pw, _browser, page):
            login(page, settings)
            page.goto(settings.patient_services_url, wait_until="domcontentloaded")
            page.select_option("select[name='clinic_id']", clinic_id)
            page.wait_for_selector("select[name='s_id']", timeout=15000)
            page.wait_for_timeout(400)
            options = select_options(page, "select[name='s_id']")
            return [o for o in options if str(o.get("value", "")).strip() not in {"", "0", "-1"}]


def search_patients(*, national_id: str, headed: bool = False) -> list[dict[str, Any]]:
    settings = get_settings(headed=headed)
    with _lock:
        with open_browser(settings) as (_pw, _browser, page):
            login(page, settings)
            return search_patients_by_national_id(page, settings, national_id)


def create_invoice_job(
    *,
    clinic: str,
    service: str,
    amount: str,
    invoice_date: str,
    national_id: str,
    headed: bool = False,
) -> dict[str, Any]:
    settings = get_settings(headed=headed)
    with _lock:
        with open_browser(settings) as (_pw, _browser, page):
            login(page, settings)
            result = run_create_and_backdate(
                page,
                settings,
                clinic=clinic,
                service=service,
                amount=str(amount),
                invoice_date=invoice_date,
                national_id=national_id,
            )
            return {
                "ok": True,
                "invoice_url": result.get("invoice_url") or result.get("edit_url") or result.get("list_url"),
                "list_url": result.get("list_url"),
                "edit_url": result.get("edit_url"),
                "rec_id": result.get("rec_id"),
                "serial": result.get("serial"),
                "st_id": result.get("st_id"),
                "patient_name": result.get("patient_name"),
                "national_id": result.get("national_id") or national_id,
                "date_updated_on_edit": bool(result.get("date_updated_on_edit")),
                "clinic": clinic,
                "service": service,
                "amount": str(amount),
                "date": invoice_date,
            }