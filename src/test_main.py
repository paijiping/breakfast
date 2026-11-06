import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from src.main import create_app


class BreakfastApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        database_path = Path(self.temporary_directory.name) / "test.sqlite3"
        self.client = TestClient(create_app(database_path))

    def tearDown(self):
        self.client.close()
        self.temporary_directory.cleanup()

    def test_menu_returns_seeded_categories_and_products(self):
        response = self.client.get("/api/menu")

        self.assertEqual(response.status_code, 200)
        menu = response.json()
        self.assertEqual(menu["categories"][0], {"id": "popular", "label": "人氣推薦"})
        self.assertEqual(menu["products"][0]["id"], "chicken-toast")
        self.assertEqual(menu["products"][0]["price"], 90)

    def test_fastapi_serves_frontend_assets(self):
        for path in ("/", "/styles.css", "/js/menu.js", "/js/order-submission.js", "/js/app.js"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_unavailable_products_are_hidden_and_cannot_be_ordered(self):
        with closing(sqlite3.connect(self.client.app.state.database_path)) as connection:
            connection.execute("UPDATE products SET is_available = 0 WHERE id = 'milk-tea'")
            connection.commit()

        menu = self.client.get("/api/menu").json()
        self.assertNotIn("milk-tea", [product["id"] for product in menu["products"]])
        response = self.client.post(
            "/api/orders",
            json={"table": "A03", "items": [{"id": "milk-tea", "quantity": 1, "note": ""}]},
        )
        self.assertEqual(response.status_code, 422)

    def test_order_uses_database_price_and_persists_order_items(self):
        response = self.client.post(
            "/api/orders",
            json={"table": " A03 ", "items": [{"id": "chicken-toast", "quantity": 2, "note": "吐司不烤"}]},
        )

        self.assertEqual(response.status_code, 201)
        order = response.json()
        self.assertEqual(order["table"], "A03")
        self.assertEqual(order["total"], 180)
        self.assertTrue(order["orderId"].startswith("ORD-"))

        with closing(sqlite3.connect(self.client.app.state.database_path)) as connection:
            stored_order = connection.execute(
                "SELECT order_number, table_number, total_amount FROM orders"
            ).fetchone()
            stored_item = connection.execute(
                "SELECT product_name, unit_price, quantity, note FROM order_items"
            ).fetchone()
        self.assertEqual(stored_order, (order["orderId"], "A03", 180))
        self.assertEqual(stored_item, ("香煎雞腿排蛋吐司", 90, 2, "吐司不烤"))

    def test_three_orders_are_persisted_independently(self):
        order_numbers = []
        for table in ("A01", "A02", "A03"):
            response = self.client.post(
                "/api/orders",
                json={"table": table, "items": [{"id": "milk-tea", "quantity": 1, "note": ""}]},
            )
            self.assertEqual(response.status_code, 201)
            order_numbers.append(response.json()["orderId"])

        self.assertEqual(len(set(order_numbers)), 3)
        with closing(sqlite3.connect(self.client.app.state.database_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 3)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM order_items").fetchone()[0], 3)

    def test_invalid_orders_are_rejected_without_partial_rows(self):
        for payload in (
            {"table": "A03", "items": []},
            {"table": "A03", "items": [{"id": "missing", "quantity": 1, "note": ""}]},
            {"table": "A03", "items": [{"id": "chicken-toast", "quantity": 0, "note": ""}]},
        ):
            response = self.client.post("/api/orders", json=payload)
            self.assertEqual(response.status_code, 422)

        with closing(sqlite3.connect(self.client.app.state.database_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM order_items").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()