import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.main import create_app


class BreakfastApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        database_path = Path(self.temporary_directory.name) / "test.sqlite3"
        with patch.dict(
            os.environ,
            {"BREAKFAST_ADMIN_USERNAME": "admin", "BREAKFAST_ADMIN_PASSWORD": "manager-secret"},
        ):
            self.client = TestClient(create_app(database_path), base_url="https://testserver")

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
        for path in (
            "/", "/styles.css", "/js/menu.js", "/js/order-submission.js", "/js/app.js",
            "/admin/login", "/admin", "/admin.css", "/js/admin-login.js", "/js/admin.js",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_admin_is_disabled_without_configured_password(self):
        database_path = Path(self.temporary_directory.name) / "disabled.sqlite3"
        with patch.dict(
            os.environ,
            {"BREAKFAST_ADMIN_USERNAME": "admin", "BREAKFAST_ADMIN_PASSWORD": ""},
        ):
            client = TestClient(create_app(database_path), base_url="https://testserver")
            try:
                self.assertEqual(client.get("/api/admin/session").status_code, 503)
                response = client.post(
                    "/api/admin/session",
                    json={"username": "admin", "password": "anything"},
                    headers={"Origin": "http://testserver"},
                )
            finally:
                client.close()
        self.assertEqual(response.status_code, 503)

    def test_default_admin_credentials_are_admin_and_1234(self):
        database_path = Path(self.temporary_directory.name) / "default-admin.sqlite3"
        with patch.dict(os.environ, {}, clear=True):
            client = TestClient(create_app(database_path), base_url="https://testserver")
        try:
            wrong_username = client.post(
                "/api/admin/session",
                json={"username": "other", "password": "1234"},
                headers={"Origin": "http://testserver"},
            )
            login = client.post(
                "/api/admin/session",
                json={"username": "admin", "password": "1234"},
                headers={"Origin": "http://testserver"},
            )
            with closing(sqlite3.connect(database_path)) as connection:
                stored_username, stored_hash = connection.execute(
                    "SELECT username, password_hash FROM admin_users"
                ).fetchone()
            self.assertEqual(stored_username, "admin")
            self.assertNotEqual(stored_hash, "1234")
            self.assertTrue(stored_hash.startswith("pbkdf2_sha256$"))

            with patch.dict(
                os.environ,
                {"BREAKFAST_ADMIN_USERNAME": "changed", "BREAKFAST_ADMIN_PASSWORD": "changed"},
            ):
                create_app(database_path)
            persisted_login = client.post(
                "/api/admin/session",
                json={"username": "admin", "password": "1234"},
                headers={"Origin": "http://testserver"},
            )
        finally:
            client.close()
        self.assertEqual(wrong_username.status_code, 401)
        self.assertEqual(login.status_code, 200)
        self.assertEqual(persisted_login.status_code, 200)

    def test_admin_session_authenticates_all_origins_and_expires_on_logout(self):
        origin = {"Origin": "http://testserver"}
        with patch.dict(os.environ, {"BREAKFAST_ADMIN_USERNAME": "admin", "BREAKFAST_ADMIN_PASSWORD": "manager-secret"}):
            invalid = self.client.post(
                "/api/admin/session", json={"username": "admin", "password": "wrong"}, headers=origin
            )
            self.assertEqual(invalid.status_code, 401)
            self.assertEqual(self.client.get("/api/admin/menu").status_code, 401)

            login = self.client.post(
                "/api/admin/session",
                json={"username": "admin", "password": "manager-secret"},
                headers={"Origin": "https://frontend.example"},
            )
            self.assertEqual(login.status_code, 200)
            self.assertTrue(login.json()["authenticated"])
            self.assertEqual(
                login.headers["access-control-allow-origin"],
                "https://frontend.example",
            )
            self.assertEqual(login.headers["access-control-allow-credentials"], "true")
            cookie_header = login.headers["set-cookie"].lower()
            self.assertIn("httponly", cookie_header)
            self.assertIn("samesite=none", cookie_header)
            self.assertIn("secure", cookie_header)
            self.assertEqual(self.client.get("/api/admin/session").status_code, 200)
            self.assertEqual(
                self.client.post(
                    "/api/admin/categories",
                    json={"label": "跨源測試"},
                    headers={"Origin": "https://frontend.example"},
                ).status_code,
                201,
            )

            logout = self.client.delete(
                "/api/admin/session",
                headers={"Origin": "https://frontend.example"},
            )
            self.assertEqual(logout.status_code, 200)
            self.assertEqual(self.client.get("/api/admin/session").status_code, 401)

    def test_cors_preflight_allows_any_origin_with_credentials(self):
        response = self.client.options(
            "/api/admin/menu",
            headers={
                "Origin": "https://frontend.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "https://frontend.example")
        self.assertEqual(response.headers["access-control-allow-credentials"], "true")
        self.assertIn("GET", response.headers["access-control-allow-methods"])

    def test_admin_can_manage_categories_and_products_without_hard_delete(self):
        origin = {"Origin": "http://testserver"}
        with patch.dict(os.environ, {"BREAKFAST_ADMIN_USERNAME": "admin", "BREAKFAST_ADMIN_PASSWORD": "manager-secret"}):
            self.client.post(
            "/api/admin/session", json={"username": "admin", "password": "manager-secret"}, headers=origin
            )
            category_response = self.client.post(
                "/api/admin/categories",
                json={"label": "季節限定", "sort_order": 9, "is_active": True},
                headers=origin,
            )
            self.assertEqual(category_response.status_code, 201)
            category_id = category_response.json()["id"]

            product_response = self.client.post(
                "/api/admin/products",
                json={
                    "category_id": category_id,
                    "name": "蜂蜜吐司",
                    "price": 60,
                    "image": "https://images.example.test/honey-toast.jpg",
                },
                headers=origin,
            )
            self.assertEqual(product_response.status_code, 201)
            product_id = product_response.json()["id"]
            invalid_image = self.client.post(
                "/api/admin/products",
                json={
                    "category_id": category_id,
                    "name": "無效圖片",
                    "price": 30,
                    "image": "http://images.example.test/item.jpg",
                },
                headers=origin,
            )
            self.assertEqual(invalid_image.status_code, 422)

            update = self.client.patch(
                "/api/admin/products/{}".format(product_id),
                json={"price": 65},
                headers=origin,
            )
            self.assertEqual(update.status_code, 200)
            self.assertEqual(update.json()["price"], 65)
            stop_product = self.client.patch(
                "/api/admin/products/{}".format(product_id),
                json={"is_available": False},
                headers=origin,
            )
            self.assertEqual(stop_product.status_code, 200)
            self.assertNotIn(
                product_id,
                [product["id"] for product in self.client.get("/api/menu").json()["products"]],
            )

            stop_category = self.client.patch(
                "/api/admin/categories/{}".format(category_id),
                json={"is_active": False},
                headers=origin,
            )
            self.assertEqual(stop_category.status_code, 200)
            admin_menu = self.client.get("/api/admin/menu").json()
            self.assertIn(category_id, [category["id"] for category in admin_menu["categories"]])
            self.assertIn(product_id, [product["id"] for product in admin_menu["products"]])

    def test_admin_can_view_order_snapshots_and_update_status(self):
        origin = {"Origin": "http://testserver"}
        with patch.dict(os.environ, {"BREAKFAST_ADMIN_USERNAME": "admin", "BREAKFAST_ADMIN_PASSWORD": "manager-secret"}):
            self.client.post(
            "/api/admin/session", json={"username": "admin", "password": "manager-secret"}, headers=origin
            )
            customer_order = self.client.post(
                "/api/orders",
                json={"table": "A03", "items": [{"id": "chicken-toast", "quantity": 1}]},
            )
            self.assertEqual(customer_order.status_code, 201)
            orders = self.client.get("/api/admin/orders").json()["orders"]
            self.assertEqual(len(orders), 1)
            order = orders[0]
            self.assertEqual(order["status"], "new")
            self.assertEqual(order["items"][0]["product_name"], "香煎雞腿排蛋吐司")
            self.assertEqual(order["items"][0]["unit_price"], 90)

            update = self.client.patch(
                "/api/admin/orders/{}".format(order["id"]),
                json={"status": "preparing"},
                headers=origin,
            )
            self.assertEqual(update.status_code, 200)
            self.assertEqual(update.json()["status"], "preparing")
            filtered = self.client.get("/api/admin/orders?status=preparing").json()["orders"]
            self.assertEqual([item["id"] for item in filtered], [order["id"]])

    def test_products_in_inactive_categories_cannot_be_ordered(self):
        origin = {"Origin": "http://testserver"}
        with patch.dict(os.environ, {"BREAKFAST_ADMIN_USERNAME": "admin", "BREAKFAST_ADMIN_PASSWORD": "manager-secret"}):
            self.client.post(
            "/api/admin/session", json={"username": "admin", "password": "manager-secret"}, headers=origin
            )
            disabled = self.client.patch(
                "/api/admin/categories/popular",
                json={"is_active": False},
                headers=origin,
            )
            self.assertEqual(disabled.status_code, 200)
            self.assertNotIn(
                "chicken-toast",
                [product["id"] for product in self.client.get("/api/menu").json()["products"]],
            )
            response = self.client.post(
                "/api/orders",
                json={"table": "A03", "items": [{"id": "chicken-toast", "quantity": 1}]},
            )
        self.assertEqual(response.status_code, 422)

    def test_existing_database_migration_preserves_orders_and_adds_default_status(self):
        database_path = Path(self.temporary_directory.name) / "legacy.sqlite3"
        with closing(sqlite3.connect(database_path)) as connection:
            connection.execute(
                """
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT NOT NULL UNIQUE,
                    table_number TEXT NOT NULL,
                    payment_method TEXT NOT NULL,
                    total_amount INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO orders (order_number, table_number, payment_method, total_amount, created_at)
                VALUES ('ORD-LEGACY-001', 'A01', 'in_store', 90, '2026-01-01T00:00:00Z')
                """
            )
            connection.commit()

        create_app(database_path)
        create_app(database_path)

        with closing(sqlite3.connect(database_path)) as connection:
            order = connection.execute(
                "SELECT order_number, table_number, total_amount, status FROM orders"
            ).fetchone()
            status_column_count = sum(
                row[1] == "status" for row in connection.execute("PRAGMA table_info(orders)")
            )
        self.assertEqual(order, ("ORD-LEGACY-001", "A01", 90, "new"))
        self.assertEqual(status_column_count, 1)

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
                "SELECT order_number, table_number, total_amount, status FROM orders"
            ).fetchone()
            stored_item = connection.execute(
                "SELECT product_name, unit_price, quantity, note FROM order_items"
            ).fetchone()
        self.assertEqual(stored_order, (order["orderId"], "A03", 180, "new"))
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