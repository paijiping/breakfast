import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, conint, constr, validator

if __package__:
    from .seed_data import MENU_CATEGORIES, MENU_PRODUCTS
else:
    from seed_data import MENU_CATEGORIES, MENU_PRODUCTS


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT_DIR / "data" / "breakfast.sqlite3"
INDEX_FILE = ROOT_DIR / "index.html"
STYLES_FILE = ROOT_DIR / "styles.css"
ADMIN_PAGE_FILE = ROOT_DIR / "admin.html"
ADMIN_LOGIN_FILE = ROOT_DIR / "admin-login.html"
ADMIN_STYLES_FILE = ROOT_DIR / "admin.css"
ADMIN_SESSION_COOKIE = "breakfast_admin_session"
ADMIN_SESSION_MAX_AGE = 8 * 60 * 60
ORDER_STATUSES = ("new", "preparing", "completed", "cancelled")


class OrderItemInput(BaseModel):
    id: constr(min_length=1, max_length=64)
    quantity: conint(ge=1, le=99)
    note: constr(max_length=80) = ""


class OrderInput(BaseModel):
    table: constr(strip_whitespace=True, min_length=1, max_length=12)
    items: List[OrderItemInput] = Field(..., min_items=1, max_items=50)


class StrictInputModel(BaseModel):
    class Config:
        extra = "forbid"


class AdminLoginInput(StrictInputModel):
    username: constr(strip_whitespace=True, min_length=1, max_length=128)
    password: constr(min_length=1, max_length=256)


class OrderStatusInput(StrictInputModel):
    status: Literal["new", "preparing", "completed", "cancelled"]


class CategoryCreateInput(StrictInputModel):
    label: constr(strip_whitespace=True, min_length=1, max_length=80)
    sort_order: conint(ge=0) = 0
    is_active: bool = True


class CategoryUpdateInput(StrictInputModel):
    label: Optional[constr(strip_whitespace=True, min_length=1, max_length=80)] = None
    sort_order: Optional[conint(ge=0)] = None
    is_active: Optional[bool] = None


class ProductFields(StrictInputModel):
    category_id: constr(min_length=1, max_length=64)
    name: constr(strip_whitespace=True, min_length=1, max_length=100)
    description: constr(max_length=500) = ""
    price: conint(ge=0)
    tag: constr(max_length=80) = ""
    image: constr(strip_whitespace=True, min_length=1, max_length=2048)
    image_position: constr(max_length=100) = "center"
    sort_order: conint(ge=0) = 0
    is_available: bool = True


class ProductCreateInput(ProductFields):
    @validator("image")
    def require_https_image(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("新商品圖片必須使用 HTTPS 網址。")
        return value


class ProductUpdateInput(ProductFields):
    category_id: Optional[constr(min_length=1, max_length=64)] = None
    name: Optional[constr(strip_whitespace=True, min_length=1, max_length=100)] = None
    description: Optional[constr(max_length=500)] = None
    price: Optional[conint(ge=0)] = None
    tag: Optional[constr(max_length=80)] = None
    image: Optional[constr(strip_whitespace=True, min_length=1, max_length=2048)] = None
    image_position: Optional[constr(max_length=100)] = None
    sort_order: Optional[conint(ge=0)] = None
    is_available: Optional[bool] = None

    @validator("image")
    def validate_existing_image_reference(cls, value):
        if value is None:
            return value
        parsed = urlsplit(value)
        if parsed.scheme == "https" and parsed.netloc:
            return value
        if value.startswith("photo-") and all(character.isalnum() or character in "-_" for character in value):
            return value
        raise ValueError("圖片必須是 HTTPS 網址或既有 Unsplash 圖片識別碼。")


def model_values(model, **kwargs):
    dump = getattr(model, "model_dump", None)
    if dump is not None:
        return dump(**kwargs)
    return model.dict(**kwargs)


def hash_admin_password(password):
    iterations = 600000
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(iterations, salt.hex(), digest.hex())


def verify_admin_password(password, encoded_hash):
    try:
        algorithm, iteration_text, salt_hex, digest_hex = encoded_hash.split("$", 3)
        iterations = int(iteration_text)
        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(digest_hex)
    except (AttributeError, TypeError, ValueError):
        return False
    if algorithm != "pbkdf2_sha256" or not 100000 <= iterations <= 1000000:
        return False
    actual_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(expected_digest, actual_digest)


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
                status TEXT NOT NULL DEFAULT 'new'
                    CHECK (status IN ('new', 'preparing', 'completed', 'cancelled')),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS admin_users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
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
        order_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(orders)").fetchall()
        }
        if "status" not in order_columns:
            connection.execute(
                """
                ALTER TABLE orders ADD COLUMN status TEXT NOT NULL DEFAULT 'new'
                    CHECK (status IN ('new', 'preparing', 'completed', 'cancelled'))
                """
            )
        existing_admin = connection.execute("SELECT 1 FROM admin_users LIMIT 1").fetchone()
        if existing_admin is None:
            admin_username = os.environ.get("BREAKFAST_ADMIN_USERNAME", "admin").strip()
            admin_password = os.environ.get("BREAKFAST_ADMIN_PASSWORD", "1234")
            if admin_username and admin_password:
                connection.execute(
                    "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
                    (admin_username, hash_admin_password(admin_password)),
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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.database_path = configured_database
    admin_session_secret = secrets.token_bytes(32)

    def has_admin_account():
        configured_username = os.environ.get("BREAKFAST_ADMIN_USERNAME", "admin").strip()
        configured_password = os.environ.get("BREAKFAST_ADMIN_PASSWORD", "1234")
        if not configured_username or not configured_password:
            return False
        with connect_database(app.state.database_path) as connection:
            return connection.execute("SELECT 1 FROM admin_users LIMIT 1").fetchone() is not None

    def issue_admin_session():
        payload = "{}.{}".format(int(time.time()), secrets.token_urlsafe(18))
        signature = hmac.new(admin_session_secret, payload.encode("utf-8"), hashlib.sha256).digest()
        encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
        return "{}.{}".format(payload, encoded_signature)

    def has_valid_admin_session(request):
        token = request.cookies.get(ADMIN_SESSION_COOKIE, "")
        try:
            issued_at, nonce, encoded_signature = token.split(".", 2)
            timestamp = int(issued_at)
            payload = "{}.{}".format(issued_at, nonce)
            expected_signature = hmac.new(
                admin_session_secret, payload.encode("utf-8"), hashlib.sha256
            ).digest()
            supplied_signature = base64.urlsafe_b64decode(
                encoded_signature + "=" * (-len(encoded_signature) % 4)
            )
        except (ValueError, TypeError):
            return False
        return (
            timestamp <= int(time.time()) + 60
            and int(time.time()) - timestamp <= ADMIN_SESSION_MAX_AGE
            and hmac.compare_digest(expected_signature, supplied_signature)
        )

    def require_admin(request: Request):
        if not has_admin_account():
            raise HTTPException(status_code=503, detail="店家管理功能尚未啟用。")
        if not has_valid_admin_session(request):
            raise HTTPException(status_code=401, detail="請先登入店家管理頁。")

    @app.get("/api/admin/session")
    def get_admin_session(request: Request):
        if not has_admin_account():
            raise HTTPException(status_code=503, detail="店家管理功能尚未啟用。")
        if not has_valid_admin_session(request):
            raise HTTPException(status_code=401, detail="管理 session 已失效。")
        return {"authenticated": True}

    @app.post("/api/admin/session")
    def create_admin_session(payload: AdminLoginInput, response: Response):
        if not has_admin_account():
            raise HTTPException(status_code=503, detail="店家管理功能尚未啟用。")
        with connect_database(app.state.database_path) as connection:
            admin = connection.execute(
                "SELECT username, password_hash FROM admin_users WHERE username = ?",
                (payload.username,),
            ).fetchone()
        if admin is None or not verify_admin_password(payload.password, admin["password_hash"]):
            raise HTTPException(status_code=401, detail="帳號或密碼不正確。")

        response.set_cookie(
            ADMIN_SESSION_COOKIE,
            issue_admin_session(),
            max_age=ADMIN_SESSION_MAX_AGE,
            httponly=True,
            secure=True,
            samesite="none",
            path="/",
        )
        return {"authenticated": True}

    @app.delete("/api/admin/session")
    def delete_admin_session(
        request: Request,
        response: Response,
        _authenticated: None = Depends(require_admin),
    ):
        response.delete_cookie(
            ADMIN_SESSION_COOKIE,
            httponly=True,
            secure=True,
            samesite="none",
            path="/",
        )
        return {"authenticated": False}

    @app.get("/api/admin/menu")
    def get_admin_menu(_authenticated: None = Depends(require_admin)):
        with connect_database(app.state.database_path) as connection:
            categories = connection.execute(
                "SELECT id, label, sort_order, is_active FROM categories ORDER BY sort_order, id"
            ).fetchall()
            products = connection.execute(
                """
                SELECT id, category_id, name, description, price, tag, image,
                       image_position, sort_order, is_available
                FROM products
                ORDER BY category_id, sort_order, id
                """
            ).fetchall()
        return {
            "categories": [dict(category) for category in categories],
            "products": [dict(product) for product in products],
        }

    @app.post("/api/admin/categories", status_code=201)
    def create_category(
        payload: CategoryCreateInput,
        _authenticated: None = Depends(require_admin),
    ):
        category_id = "cat-{}".format(secrets.token_hex(8))
        try:
            with connect_database(app.state.database_path) as connection:
                connection.execute(
                    "INSERT INTO categories (id, label, sort_order, is_active) VALUES (?, ?, ?, ?)",
                    (category_id, payload.label, payload.sort_order, int(payload.is_active)),
                )
        except sqlite3.IntegrityError as error:
            raise HTTPException(status_code=422, detail="分類資料不符合限制。") from error
        return {"id": category_id, **model_values(payload), "is_active": int(payload.is_active)}

    @app.patch("/api/admin/categories/{category_id}")
    def update_category(
        category_id: str,
        payload: CategoryUpdateInput,
        _authenticated: None = Depends(require_admin),
    ):
        updates = model_values(payload, exclude_unset=True)
        if not updates or any(value is None for value in updates.values()):
            raise HTTPException(status_code=422, detail="至少需提供一個有效的分類欄位。")
        if "is_active" in updates:
            updates["is_active"] = int(updates["is_active"])
        updates["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
        with connect_database(app.state.database_path) as connection:
            exists = connection.execute("SELECT 1 FROM categories WHERE id = ?", (category_id,)).fetchone()
            if exists is None:
                raise HTTPException(status_code=404, detail="分類不存在。")
            assignments = ", ".join("{} = ?".format(column) for column in updates)
            connection.execute(
                "UPDATE categories SET {} WHERE id = ?".format(assignments),
                (*updates.values(), category_id),
            )
            category = connection.execute(
                "SELECT id, label, sort_order, is_active FROM categories WHERE id = ?",
                (category_id,),
            ).fetchone()
        return dict(category)

    @app.post("/api/admin/products", status_code=201)
    def create_product(
        payload: ProductCreateInput,
        _authenticated: None = Depends(require_admin),
    ):
        product_id = "prd-{}".format(secrets.token_hex(8))
        values = model_values(payload)
        values["is_available"] = int(values["is_available"])
        try:
            with connect_database(app.state.database_path) as connection:
                category = connection.execute(
                    "SELECT 1 FROM categories WHERE id = ?", (payload.category_id,)
                ).fetchone()
                if category is None:
                    raise HTTPException(status_code=422, detail="商品分類不存在。")
                connection.execute(
                    """
                    INSERT INTO products (
                        id, category_id, name, description, price, tag, image,
                        image_position, sort_order, is_available
                    ) VALUES (
                        :id, :category_id, :name, :description, :price, :tag, :image,
                        :image_position, :sort_order, :is_available
                    )
                    """,
                    {"id": product_id, **values},
                )
        except sqlite3.IntegrityError as error:
            raise HTTPException(status_code=422, detail="商品資料不符合限制。") from error
        return {"id": product_id, **values}

    @app.patch("/api/admin/products/{product_id}")
    def update_product(
        product_id: str,
        payload: ProductUpdateInput,
        _authenticated: None = Depends(require_admin),
    ):
        updates = model_values(payload, exclude_unset=True)
        if not updates or any(value is None for value in updates.values()):
            raise HTTPException(status_code=422, detail="至少需提供一個有效的商品欄位。")

        with connect_database(app.state.database_path) as connection:
            current = connection.execute(
                "SELECT image FROM products WHERE id = ?", (product_id,)
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="商品不存在。")
            if "image" in updates and updates["image"].startswith("photo-"):
                if updates["image"] != current["image"]:
                    raise HTTPException(status_code=422, detail="新商品圖片必須使用 HTTPS 網址。")
            if "category_id" in updates:
                category = connection.execute(
                    "SELECT 1 FROM categories WHERE id = ?", (updates["category_id"],)
                ).fetchone()
                if category is None:
                    raise HTTPException(status_code=422, detail="商品分類不存在。")
            if "is_available" in updates:
                updates["is_available"] = int(updates["is_available"])
            updates["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
            assignments = ", ".join("{} = ?".format(column) for column in updates)
            try:
                connection.execute(
                    "UPDATE products SET {} WHERE id = ?".format(assignments),
                    (*updates.values(), product_id),
                )
            except sqlite3.IntegrityError as error:
                raise HTTPException(status_code=422, detail="商品資料不符合限制。") from error
            product = connection.execute(
                """
                SELECT id, category_id, name, description, price, tag, image,
                       image_position, sort_order, is_available
                FROM products WHERE id = ?
                """,
                (product_id,),
            ).fetchone()
        return dict(product)

    @app.get("/api/admin/orders")
    def get_admin_orders(
        status: Optional[str] = Query(None),
        _authenticated: None = Depends(require_admin),
    ):
        if status is not None and status not in ORDER_STATUSES:
            raise HTTPException(status_code=422, detail="訂單狀態無效。")
        with connect_database(app.state.database_path) as connection:
            if status is None:
                orders = connection.execute(
                    "SELECT * FROM orders ORDER BY created_at DESC, id DESC"
                ).fetchall()
            else:
                orders = connection.execute(
                    "SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC, id DESC",
                    (status,),
                ).fetchall()
            items = connection.execute(
                """
                SELECT order_id, product_id, product_name, unit_price, quantity, note
                FROM order_items ORDER BY id
                """
            ).fetchall()
        items_by_order = {}
        for item in items:
            items_by_order.setdefault(item["order_id"], []).append(
                {key: item[key] for key in item.keys() if key != "order_id"}
            )
        result = []
        for order in orders:
            order_data = dict(order)
            order_data["items"] = items_by_order.get(order["id"], [])
            result.append(order_data)
        return {"orders": result}

    @app.patch("/api/admin/orders/{order_id}")
    def update_order_status(
        order_id: int,
        payload: OrderStatusInput,
        _authenticated: None = Depends(require_admin),
    ):
        with connect_database(app.state.database_path) as connection:
            cursor = connection.execute(
                "UPDATE orders SET status = ? WHERE id = ?", (payload.status, order_id)
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="訂單不存在。")
            order = connection.execute(
                "SELECT id, order_number, table_number, total_amount, status, created_at FROM orders WHERE id = ?",
                (order_id,),
            ).fetchone()
        return dict(order)

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
                        """
                        SELECT p.id, p.name, p.price
                        FROM products AS p
                        JOIN categories AS c ON c.id = p.category_id
                        WHERE p.id = ? AND p.is_available = 1 AND c.is_active = 1
                        """,
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

    @app.get("/admin/login")
    def serve_admin_login():
        return FileResponse(ADMIN_LOGIN_FILE)

    @app.get("/admin")
    def serve_admin():
        return FileResponse(ADMIN_PAGE_FILE)

    @app.get("/admin.css")
    def serve_admin_styles():
        return FileResponse(ADMIN_STYLES_FILE, media_type="text/css")

    app.mount("/js", StaticFiles(directory=ROOT_DIR / "js"), name="javascript")
    return app


app = create_app()