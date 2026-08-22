import unittest

from app import app
from config import DATABASE_URL


@unittest.skipUnless(DATABASE_URL, "Configurare DATABASE_URL ed eseguire l'importazione")
class AppTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_home_and_autocomplete(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        response = self.client.get("/api/stops?q=Ecotekne")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any("Ecotekne" in item["stop_name"] for item in response.json))

    def test_known_direct_journey(self):
        response = self.client.get(
            "/search?from_stop=extraurbano:1&to_stop=extraurbano:326"
            "&date=2026-08-24&time=00:00"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"07:30", response.data)
        self.assertIn(b"08:55", response.data)


if __name__ == "__main__":
    unittest.main()
