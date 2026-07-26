import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    base_url: str
    username: str
    password: str
    patient_services_url: str
    headed: bool
    slow_mo_ms: int

    @property
    def login_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/login.php"

    @property
    def home_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/setting6.php"


def load_settings() -> Settings:
    username = os.getenv("CLINIC_USERNAME", "").strip()
    password = os.getenv("CLINIC_PASSWORD", "").strip()
    if not username or not password:
        raise RuntimeError(
            "Missing CLINIC_USERNAME / CLINIC_PASSWORD. "
            "Copy .env.example to .env and fill in your credentials."
        )

    return Settings(
        base_url=os.getenv("CLINIC_BASE_URL", "https://rode.imdad.cloud/medica13").strip(),
        username=username,
        password=password,
        patient_services_url=os.getenv(
            "PATIENT_SERVICES_URL",
            "https://rode.imdad.cloud/medica13/patient_services_add.php?st_id=37917",
        ).strip(),
        headed=_bool(os.getenv("HEADED", "1"), default=True),
        slow_mo_ms=int(os.getenv("SLOW_MO_MS", "100") or "100"),
    )