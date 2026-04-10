import tempfile
import unittest
from pathlib import Path

from app import create_app, get_db


class CertificateClaimAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": str(temp_path / "test.db"),
                "OUTPUT_DIR": str(temp_path / "output"),
                "SECRET_KEY": "test-secret",
            }
        )
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_code(self) -> str:
        response = self.client.post("/admin", data={"quantity": "1", "label": "batch-a"})
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            row = get_db().execute(
                "SELECT code FROM claim_codes ORDER BY datetime(created_at) DESC LIMIT 1"
            ).fetchone()
        self.assertIsNotNone(row)
        return row["code"]

    def test_code_can_only_be_claimed_once(self) -> None:
        code = self.create_code()

        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Claim your PDF certificate", response.data)

        response = self.client.post("/", data={"code": code, "name": "Murad Orujov"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")

        response = self.client.post("/", data={"code": code, "name": "Murad Orujov"})
        self.assertEqual(response.status_code, 410)
        self.assertIn(b"already been used", response.data)

    def test_invalid_name_is_rejected(self) -> None:
        code = self.create_code()
        response = self.client.post("/", data={"code": code, "name": "1"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"recipient name", response.data)

    def test_invalid_code_is_rejected(self) -> None:
        response = self.client.post("/", data={"code": "ABCD-1234", "name": "Murad Orujov"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"invalid", response.data)


if __name__ == "__main__":
    unittest.main()
