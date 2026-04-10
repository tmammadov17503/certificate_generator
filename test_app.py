import unittest

from app import create_app


class CertificateClaimAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(
            {
                "TESTING": True,
            }
        )
        self.client = self.app.test_client()

    def test_home_page_loads(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Download your PDF certificate", response.data)

    def test_valid_name_downloads_pdf(self) -> None:
        response = self.client.post("/", data={"name": "Murad Orujov"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")

    def test_invalid_name_is_rejected(self) -> None:
        response = self.client.post("/", data={"name": "1"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"recipient name", response.data)

    def test_legacy_admin_route_redirects_to_public_page(self) -> None:
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/") or response.headers["Location"].endswith("/claim"))


if __name__ == "__main__":
    unittest.main()
