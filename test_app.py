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

    def create_link(self) -> str:
        response = self.client.post("/", data={"quantity": "1", "label": "batch-a"})
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            row = get_db().execute(
                "SELECT token FROM claim_links ORDER BY datetime(created_at) DESC LIMIT 1"
            ).fetchone()
        self.assertIsNotNone(row)
        return row["token"]

    def test_link_can_only_be_claimed_once(self) -> None:
        token = self.create_link()

        response = self.client.get(f"/claim/{token}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Claim your PDF certificate", response.data)

        response = self.client.post(f"/claim/{token}", data={"name": "Murad Orujov"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")

        response = self.client.get(f"/claim/{token}")
        self.assertEqual(response.status_code, 410)
        self.assertIn(b"already been used", response.data)

    def test_invalid_name_is_rejected(self) -> None:
        token = self.create_link()
        response = self.client.post(f"/claim/{token}", data={"name": "1"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"recipient name", response.data)


if __name__ == "__main__":
    unittest.main()
