import unittest

from clinic_invoice_bot.api_ops import (
    public_error,
    recall_recent_invoice,
    remember_recent_invoice,
    _invoice_key,
    _recent_success,
)
from clinic_invoice_bot.workflow import (
    bank_transfer_fields,
    bank_transfer_option_value,
    registration_is_complete,
    validate_patient_registration,
)


class RegistrationTests(unittest.TestCase):
    def test_valid_registration(self) -> None:
        fields = validate_patient_registration(
            national_id="1234567890",
            name="  Sara   Ali ",
            birth_date="1992-03-20",
            phone="0551112233",
            gender="female",
            nationality="1",
        )
        self.assertEqual(fields["national_id"], "1234567890")
        self.assertEqual(fields["name"], "Sara Ali")
        self.assertEqual(fields["gender"], "2")
        self.assertEqual(fields["day"], "20")
        self.assertEqual(fields["nationality"], "1")

    def test_invalid_national_id(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "10 أرقام"):
            validate_patient_registration(
                national_id="123",
                name="Sara Ali",
                birth_date="1992-03-20",
                phone="0551112233",
                gender="1",
                nationality="1",
            )

    def test_invalid_phone_and_future_birth_date(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "الجوال"):
            validate_patient_registration(
                national_id="1234567890",
                name="Sara Ali",
                birth_date="1992-03-20",
                phone="12",
                gender="1",
                nationality="1",
            )
        with self.assertRaisesRegex(RuntimeError, "الميلاد"):
            validate_patient_registration(
                national_id="1234567890",
                name="Sara Ali",
                birth_date="2099-01-01",
                phone="0551112233",
                gender="1",
                nationality="1",
            )

    def test_registration_requires_every_field(self) -> None:
        self.assertFalse(
            registration_is_complete(
                name="Sara",
                birth_date="1992-03-20",
                phone="0551112233",
                gender="1",
                nationality="",
            )
        )
        self.assertTrue(
            registration_is_complete(
                name="Sara",
                birth_date="1992-03-20",
                phone="0551112233",
                gender="1",
                nationality="27",
            )
        )


class PaymentTests(unittest.TestCase):
    def test_bank_transfer_fields(self) -> None:
        fields = bank_transfer_fields("150")
        self.assertEqual(fields["cash_amount"], "0.00")
        self.assertEqual(fields["net_amount"], "150")
        self.assertEqual(fields["bank_label"], "تحويل بنكي")
        self.assertEqual(fields["bank_value"], "1232")

    def test_bank_option_uses_the_label_seen_in_imdad(self) -> None:
        value = bank_transfer_option_value(
            [
                {"value": "1232", "text": "تحويل بنكي"},
                {"value": "1398", "text": "VISA"},
                {"value": "1397", "text": "MADA"},
            ]
        )
        self.assertEqual(value, "1232")

    def test_missing_bank_option_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "تحويل بنكي"):
            bank_transfer_option_value([{"value": "1398", "text": "VISA"}])


class ReliabilityTests(unittest.TestCase):
    def tearDown(self) -> None:
        _recent_success.clear()

    def test_recent_invoice_is_reused_instead_of_created_again(self) -> None:
        key = _invoice_key("1234567890", "82", "2510", "100", "2026-01-15")
        remember_recent_invoice(key, {"serial": "9", "payment_method": "تحويل بنكي"})
        self.assertEqual(recall_recent_invoice(key)["serial"], "9")

    def test_connection_errors_are_arabic_and_hide_details(self) -> None:
        message = public_error(TimeoutError("Timeout 30000ms exceeded"))
        self.assertIn("إمداد", message)
        self.assertNotIn("30000", message)


if __name__ == "__main__":
    unittest.main()
