import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, constr, conint

if __package__:
    from .seed_data import MENU_CATEGORIES, MENU_PRODUCTS
else:
    from seed_data import MENU_CATEGORIES, MENU_PRODUCTS


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT_DIR / "data" / "breakfast.sqlite3"
INDEX_FILE = ROOT_DIR / "index.html"
STYLES_FILE = ROOT_DIR / "styles.css"


class OrderItemInput(BaseModel):
    id: constr(min_length=1, max_length=64)
    quantity: conint(ge=1, le=99)
    note: constr(max_length=80) = ""


class OrderInput(BaseModel):
    table: constr(strip_whitespace=True, min_length=1, max_length=12)
    items: List[OrderItemInput] = Field(..., min_items=1, max_items=50)


@contextmanager
def connect_database(database_path):
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(database_path):
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    with connect_database(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                category_id TEXT NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                price INTEGER NOT NULL CHECK (price >= 0),
                tag TEXT NOT NULL DEFAULT '',
                image TEXT NOT NULL,
                image_position TEXT NOT NULL DEFAULT 'center',
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_available INTEGER NOT NULL DEFAULT 1 CHECK (is_available IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT NOT NULL UNIQUE,
                table_number TEXT NOT NULL CHECK (length(table_number) BETWEEN 1 AND 12),
                payment_method TEXT NOT NULL CHECK (payment_method = 'in_store'),
                total_amount INTEGER NOT NULL CHECK (total_amount >= 0),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                product_id TEXT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
                product_name TEXT NOT NULL,
                unit_price INTEGER NOT NULL CHECK (unit_price >= 0),
                quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 99),
                note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 80)
            );

            CREATE INDEX IF NOT EXISTS idx_products_category_available_sort
                ON products(category_id, is_available, sort_order);
            CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
            CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
            """
        )
        existing_categories = connection.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        if existing_categories == 0:
            connection.executemany(
                "INSERT INTO categories (id, label, sort_order) VALUES (:id, :label, :sort_order)",
                MENU_CATEGORIES,
            )
            connection.executemany(
                """
                INSERT INTO products (
                    id, category_id, name, description, price, tag, image, image_position, sort_order
                ) VALUES (
                    :id, :category_id, :name, :description, :price, :tag, :image, :image_position, :sort_order
                )
                """,
                MENU_PRODUCTS,
            )


def create_app(database_path=None):
    configured_database = database_path or os.environ.get("BREAKFAST_DB_PATH", DEFAULT_DATABASE)
    configured_database = Path(configured_database)
    initialize_database(configured_database)

    app = FastAPI(title="早餐店點餐 API", version="1.0.0")
    app.state.database_path = configured_database

    @app.get("/api/menu")
    def get_menu():
        with connect_database(app.state.database_path) as connection:
            categories = connection.execute(
                "SELECT id, label FROM categories WHERE is_active = 1 ORDER BY sort_order, id"
            ).fetchall()
            products = connection.execute(
                """
                SELECT p.id, p.category_id AS category, p.name, p.description, p.price,
                       p.tag, p.image, p.image_position AS imagePosition
                FROM products AS p
                JOIN categories AS c ON c.id = p.category_id
                WHERE p.is_available = 1 AND c.is_active = 1
                ORDER BY c.sort_order, p.sort_order, p.id
                """
            ).fetchall()
        return {
            "categories": [dict(category) for category in categories],
            "products": [dict(product) for product in products],
        }

    @app.post("/api/orders", status_code=201)
    def create_order(order: OrderInput):
        now = datetime.now(timezone.utc)
        order_number = "ORD-{}-{}".format(now.strftime("%Y%m%d"), secrets.token_hex(3).upper())
        normalized_table = order.table.strip()
        try:
            with connect_database(app.state.database_path) as connection:
                products = {}
                total = 0
                for item in order.items:
                    product = connection.execute(
                        "SELECT id, name, price FROM products WHERE id = ? AND is_available = 1",
                        (item.id,),
                    ).fetchone()
                    if product is None:
                        raise HTTPException(status_code=422, detail="餐點不存在或目前未供應。")
                    products[item.id] = product
                    total += product["price"] * item.quantity

                cursor = connection.execute(
                    """
                    INSERT INTO orders (order_number, table_number, payment_method, total_amount)
                    VALUES (?, ?, 'in_store', ?)
                    """,
                    (order_number, normalized_table, total),
                )
                order_id = cursor.lastrowid
                connection.executemany(
                    """
                    INSERT INTO order_items (order_id, product_id, product_name, unit_price, quantity, note)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (order_id, item.id, products[item.id]["name"], products[item.id]["price"], item.quantity, item.note.strip())
                        for item in order.items
                    ],
                )
        except sqlite3.IntegrityError as error:
            raise HTTPException(status_code=422, detail="訂單資料不符合限制。") from error

        return {"ok": True, "orderId": order_number, "table": normalized_table, "total": total}

    @app.get("/")
    def serve_index():
        return FileResponse(INDEX_FILE)

    @app.get("/styles.css")
    def serve_styles():
        return FileResponse(STYLES_FILE, media_type="text/css")

    app.mount("/js", StaticFiles(directory=ROOT_DIR / "js"), name="javascript")
    return app


app = create_app()