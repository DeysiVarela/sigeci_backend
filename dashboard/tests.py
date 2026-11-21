from django.test import TestCase, Client


class DashboardApiTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_get_dashboard_metrics(self):
        response = self.client.get("/api/v1/dashboard/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("sql_query", data)
        self.assertIn("data", data)
        metrics = data["data"]
        self.assertIn("new_orders", metrics)
        self.assertIn("bounce_rate", metrics)
        self.assertIn("user_registrations", metrics)
        self.assertIn("unique_visitors", metrics)
        self.assertIn("total_articles", metrics)
