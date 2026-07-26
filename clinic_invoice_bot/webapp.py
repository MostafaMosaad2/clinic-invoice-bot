import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .api_ops import (
    create_invoice_job,
    fetch_clinics,
    fetch_services,
    patient_meta,
    search_patients,
)

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
executor = ThreadPoolExecutor(max_workers=1)

app = FastAPI(title="Clinic Invoice Bot", version="0.1.0")


class CreateInvoiceBody(BaseModel):
    national_id: str = Field(..., min_length=5)
    clinic: str = Field(..., min_length=1)
    service: str = Field(..., min_length=1)
    amount: str = Field(..., min_length=1)
    date: str = Field(..., min_length=4)
    headed: bool = False


def _headed_default() -> bool:
    return os.getenv("WEB_HEADED", "0").strip().lower() in {"1", "true", "yes", "on"}


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"ok": True}


@app.get("/api/meta")
def meta() -> Dict[str, Any]:
    try:
        return patient_meta()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/patients")
def patients(
    national_id: str = Query(..., min_length=5),
    headed: Optional[bool] = Query(default=None),
) -> Dict[str, Any]:
    use_headed = _headed_default() if headed is None else headed
    try:
        items = executor.submit(
            search_patients,
            national_id=national_id,
            headed=use_headed,
        ).result()
        return {"items": items}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/clinics")
def clinics(headed: Optional[bool] = Query(default=None)) -> Dict[str, Any]:
    use_headed = _headed_default() if headed is None else headed
    try:
        items = executor.submit(fetch_clinics, headed=use_headed).result()
        return {"items": items}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/services")
def services(
    clinic_id: str = Query(...),
    headed: Optional[bool] = Query(default=None),
) -> Dict[str, Any]:
    use_headed = _headed_default() if headed is None else headed
    try:
        items = executor.submit(fetch_services, clinic_id, headed=use_headed).result()
        return {"items": items}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/invoices")
def create_invoice(body: CreateInvoiceBody) -> Dict[str, Any]:
    use_headed = body.headed or _headed_default()
    try:
        result = executor.submit(
            create_invoice_job,
            national_id=body.national_id,
            clinic=body.clinic,
            service=body.service,
            amount=body.amount,
            invoice_date=body.date,
            headed=use_headed,
        ).result()
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


if WEB_ROOT.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_ROOT / "static")), name="static")