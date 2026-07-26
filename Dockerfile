FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HEADED=0 \
    WEB_HEADED=0 \
    SLOW_MO_MS=0

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY clinic_invoice_bot ./clinic_invoice_bot
COPY web ./web

EXPOSE 8000

CMD ["sh", "-c", "uvicorn clinic_invoice_bot.webapp:app --host 0.0.0.0 --port ${PORT:-8000}"]
