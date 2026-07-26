# clinic-invoice-bot

Python + Playwright bot for the IMDAD clinic system at `rode.imdad.cloud/medica13`.

## What it does

1. Logs in
2. Opens `patient_services_add.php?st_id=...`
3. Selects **clinic** and **service**, clicks **Add**
4. Fills **cash amount** and the invoice **date** (day/month/year)
5. Finalizes the invoice
6. Re-opens the new invoice from the patient invoices list and tries to update the date again

## Setup

```powershell
cd $env:USERPROFILE\clinic-invoice-bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
copy .env.example .env
```

Edit `.env`:

```
CLINIC_USERNAME=...
CLINIC_PASSWORD=...
PATIENT_SERVICES_URL=https://rode.imdad.cloud/medica13/patient_services_add.php?st_id=37917
```

## Web UI

```powershell
cd $env:USERPROFILE\clinic-invoice-bot
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn clinic_invoice_bot.webapp:app --reload --port 8787
```

Open [http://127.0.0.1:8787](http://127.0.0.1:8787).

The UI loads clinics/services from IMDAD, then runs create + date set.

## CLI usage

Interactive create (prompts for clinic, service, amount, date):

```powershell
python -m clinic_invoice_bot create
```

Non-interactive example:

```powershell
python -m clinic_invoice_bot create --clinic COSMOTOLOGY --service "Moon Light" --amount 100 --date 2026-01-15
```

Inspect clinics/services:

```powershell
python -m clinic_invoice_bot inspect
```

Change date on an existing invoice URL:

```powershell
python -m clinic_invoice_bot edit-date --url "https://rode.imdad.cloud/medica13/recs.php?sid=37917" --date 2026-01-15
```

## Notes

- Credentials stay in `.env` (gitignored).
- Browser runs headed by default (`HEADED=1`).
- This account may get **Forbidden Permission** on `rec_edit.php` / `reck_edit.php`. In that case the date is still applied on the create/finalize form (`day8` / `month8` / `year8`).
- Do not create test invoices on a live patient unless you intend to.