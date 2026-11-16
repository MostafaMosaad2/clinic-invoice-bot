from __future__ import annotations

import threading
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

from .browser import open_browser
from .config import Settings, load_settings
from .workflow import (
    PatientFileRequired,
    login,
    registration_is_complete,
    run_create_and_backdate,
    search_patients_by_national_id,
    select_options,
)

_lock = threading.Lock()
_recent_success: dict[tuple[str, str, str, str, str], tuple[float, dict[str, Any]]] = {}
_RECENT_SECONDS = 600


def _invoice_key(national_id: str, clinic: str, service: str, amount: str, invoice_date: str) -> tuple[str, str, str, str, str]:
    return (national_id, clinic, service, amount, invoice_date)


def recall_recent_invoice(key: tuple[str, str, str, str, str]) -> dict[str, Any] | None:
    hit = _recent_success.get(key)
    if not hit:
        return None
    saved_at, payload = hit
    if time.time() - saved_at > _RECENT_SECONDS:
        _recent_success.pop(key, None)
        return None
    return payload


def remember_recent_invoice(key: tuple[str, str, str, str, str], payload: dict[str, Any]) -> None:
    now = time.time()
    stale = [item for item, (saved_at, _) in _recent_success.items() if now - saved_at > _RECENT_SECONDS]
    for item in stale:
        _recent_success.pop(item, None)
    _recent_success[key] = (now, payload)


def public_error(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if "انتهت جلسة" in text or "login.php" in lowered or "session" in lowered:
        return "انتهت جلسة إمداد. أعد المحاولة."
    if "timeout" in lowered or "net::" in lowered or "err_" in lowered or "connection" in lowered:
        return "تعذر الاتصال بنظام إمداد. أعد المحاولة."
    if any("\u0600" <= char <= "\u06FF" for char in text):
        return text
    return "تعذر إكمال العملية في إمداد. لم تُنشأ فاتورة جديدة."


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


def _invoice_result(
    *,
    result: dict[str, Any],
    clinic: str,
    service: str,
    amount: str,
    invoice_date: str,
    national_id: str,
) -> dict[str, Any]:
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
        "file_created": bool(result.get("file_created")),
        "reused": bool(result.get("reused")),
        "payment_method": result.get("payment_method") or "تحويل بنكي",
    }


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
            return _invoice_result(
                result=result,
                clinic=clinic,
                service=service,
                amount=amount,
                invoice_date=invoice_date,
                national_id=national_id,
            )


def create_invoices_batch(
    *,
    items: list[dict[str, Any]],
    headed: bool = False,
) -> dict[str, Any]:
    """
    Create many invoices in one browser session.
    Patients with no IMDAD file go into missing_files instead of aborting the batch.
    """
    settings = get_settings(headed=headed)
    created: list[dict[str, Any]] = []
    missing_files: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    with _lock:
        with open_browser(settings) as (_pw, _browser, page):
            login(page, settings)
            for index, item in enumerate(items):
                national_id = str(item.get("national_id") or "").strip()
                clinic = str(item.get("clinic") or "").strip()
                service = str(item.get("service") or "").strip()
                amount = str(item.get("amount") or "").strip()
                invoice_date = str(item.get("date") or "").strip()
                patient_name = str(item.get("name") or "").strip()
                birth_date = str(item.get("birth_date") or "").strip()
                phone = str(item.get("phone") or "").strip()
                gender = str(item.get("gender") or "").strip()
                nationality = str(item.get("nationality") or "").strip()
                row = {
                    "index": index,
                    "national_id": national_id,
                    "clinic": clinic,
                    "service": service,
                    "amount": amount,
                    "date": invoice_date,
                }

                if not national_id or not clinic or not service or not amount or not invoice_date:
                    errors.append({**row, "error": "بيانات الفاتورة غير مكتملة."})
                    continue

                invoice_key = _invoice_key(national_id, clinic, service, amount, invoice_date)
                remembered = recall_recent_invoice(invoice_key)
                if remembered:
                    created.append(dict(remembered))
                    continue

                try:
                    matches = search_patients_by_national_id(page, settings, national_id)
                    file_ready = registration_is_complete(
                        name=patient_name,
                        birth_date=birth_date,
                        phone=phone,
                        gender=gender,
                        nationality=nationality,
                    )
                    if not matches and not file_ready:
                        missing_files.append(
                            {
                                **row,
                                "reason": "لم يتم العثور على ملف المريض.",
                            }
                        )
                        continue

                    patient = matches[0] if matches else None
                    result = run_create_and_backdate(
                        page,
                        settings,
                        clinic=clinic,
                        service=service,
                        amount=amount,
                        invoice_date=invoice_date,
                        national_id=national_id,
                        st_id=None if not patient else patient.get("st_id"),
                        **(
                            {}
                            if patient
                            else {
                                "patient_name": patient_name,
                                "birth_date": birth_date,
                                "phone": phone,
                                "gender": gender,
                                "nationality": nationality,
                            }
                        ),
                    )
                    payload = _invoice_result(
                        result=result,
                        clinic=clinic,
                        service=service,
                        amount=amount,
                        invoice_date=invoice_date,
                        national_id=national_id,
                    )
                    known = patient or {}
                    payload["patient_name"] = (
                        known.get("name") or payload.get("patient_name") or patient_name
                    )
                    payload["st_id"] = known.get("st_id") or payload.get("st_id")
                    created.append(payload)
                    remember_recent_invoice(invoice_key, payload)
                except PatientFileRequired:
                    missing_files.append({**row, "reason": "لم يتم العثور على ملف المريض."})
                except Exception as exc:
                    errors.append({**row, "error": public_error(exc)})

    return {
        "ok": True,
        "created": created,
        "missing_files": missing_files,
        "errors": errors,
        "created_count": len(created),
        "missing_count": len(missing_files),
        "error_count": len(errors),
    }