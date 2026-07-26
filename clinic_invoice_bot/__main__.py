from __future__ import annotations

import argparse
import sys

from .browser import open_browser
from .config import load_settings
from .forms import ask
from .workflow import inspect_patient_services, login, run_create_and_backdate, update_invoice_date


def _pause() -> None:
    try:
        if sys.stdin.isatty():
            input("\nPress Enter to close the browser...")
    except EOFError:
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a clinic invoice, then set/change its date."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser(
        "create",
        help="Login, create invoice (clinic/service/amount), then set date",
    )
    create.add_argument("--national-id", help="Patient national ID / SSN")
    create.add_argument("--clinic", help="Clinic value or name (optional; prompted if omitted)")
    create.add_argument("--service", help="Service value or name (optional; prompted if omitted)")
    create.add_argument("--amount", help="Cash amount paid")
    create.add_argument("--date", help="Invoice date YYYY-MM-DD or DD/MM/YYYY")

    sub.add_parser("inspect", help="Login and list clinics/services/date fields")

    edit = sub.add_parser("edit-date", help="Open an invoice URL and change its date")
    edit.add_argument("--url", required=True, help="Invoice edit/view/list URL")
    edit.add_argument("--date", required=False, help="New date value")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()

    with open_browser(settings) as (_pw, _browser, page):
        login(page, settings)

        if args.command == "inspect":
            inspect_patient_services(page, settings)
            _pause()
            return 0

        if args.command == "edit-date":
            new_date = args.date or ask("New invoice date (YYYY-MM-DD or DD/MM/YYYY)")
            ok = update_invoice_date(page, args.url, new_date, settings=settings)
            _pause()
            return 0 if ok else 2

        if args.command == "create":
            run_create_and_backdate(
                page,
                settings,
                national_id=args.national_id,
                clinic=args.clinic,
                service=args.service,
                amount=args.amount,
                invoice_date=args.date,
            )
            _pause()
            return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())