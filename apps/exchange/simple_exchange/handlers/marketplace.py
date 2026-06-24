"""Marketplace offer/order CRUD handlers."""

import random
import sqlite3
import urllib.parse
from datetime import UTC, datetime

from ..db import get_db_path


class MarketplaceMixin:
    """Marketplace offer and order management methods."""

    def _new_marketplace_id(self, prefix):
        return f"{prefix}_{int(datetime.now(UTC).timestamp() * 1000)}{random.randint(100, 999)}"

    def _marketplace_offer_row(self, row):
        return {
            "id": row[0],
            "address": row[0],
            "item": row[1],
            "item_type": row[2],
            "model": row[2],
            "price": row[3],
            "price_per_hour": row[3],
            "wallet": row[4],
            "status": row[5],
            "description": row[6],
            "created_at": row[7],
            "deployed_at": row[7],
        }

    def _marketplace_order_row(self, row):
        return {
            "id": row[0],
            "order_type": row[1],
            "item": row[2],
            "price": row[3],
            "wallet": row[4],
            "status": row[5],
            "created_at": row[6],
        }

    def handle_marketplace_offers(self, parsed):
        query = urllib.parse.parse_qs(parsed.query)
        status_filter = query.get("status", [None])[0]
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        if status_filter:
            cursor.execute(
                """
                SELECT id, item, item_type, price, wallet, status, description, created_at
                FROM marketplace_offers
                WHERE status = ?
                ORDER BY created_at DESC
            """,
                (status_filter,),
            )
        else:
            cursor.execute("""
                SELECT id, item, item_type, price, wallet, status, description, created_at
                FROM marketplace_offers
                ORDER BY created_at DESC
            """)
        offers = [self._marketplace_offer_row(row) for row in cursor.fetchall()]
        conn.close()
        self.send_json_response(offers)

    def handle_marketplace_offer(self, path):
        offer_id = urllib.parse.unquote(path.rsplit("/", 1)[-1])
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, item, item_type, price, wallet, status, description, created_at
            FROM marketplace_offers
            WHERE id = ?
        """,
            (offer_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            self.send_json_response(self._marketplace_offer_row(row))
        else:
            self.send_error(404, "Offer not found")

    def handle_marketplace_create_offer(self):
        try:
            data = self._read_json_body()
            item = data.get("item") or data.get("item_type") or "service"
            item_type = data.get("item_type") or item
            price = float(data.get("price") or data.get("price_per_hour") or 0)
            wallet = data.get("wallet")
            description = data.get("description", "")
            offer_id = self._new_marketplace_id("offer")
            order_id = self._new_marketplace_id("order")
            db_path = get_db_path()
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO marketplace_offers (id, item, item_type, price, wallet, status, description)
                VALUES (?, ?, ?, ?, ?, 'active', ?)
            """,
                (offer_id, item, item_type, price, wallet, description),
            )
            cursor.execute(
                """
                INSERT INTO marketplace_orders (id, order_type, item, price, wallet, status)
                VALUES (?, 'SELL', ?, ?, ?, 'open')
            """,
                (order_id, item, price, wallet),
            )
            conn.commit()
            cursor.execute(
                """
                SELECT id, item, item_type, price, wallet, status, description, created_at
                FROM marketplace_offers
                WHERE id = ?
            """,
                (offer_id,),
            )
            offer = self._marketplace_offer_row(cursor.fetchone())
            conn.close()
            offer["order_id"] = order_id
            self.send_json_response(offer, status=201)
        except Exception as e:
            self.send_json_response({"success": False, "error": str(e)}, status=400)

    def handle_marketplace_book_offer(self, path):
        try:
            offer_id = urllib.parse.unquote(path[len("/v1/marketplace/offers/") : -len("/book")])
            data = self._read_json_body()
            wallet = data.get("wallet")
            db_path = get_db_path()
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT item, price
                FROM marketplace_offers
                WHERE id = ? OR item = ?
            """,
                (offer_id, offer_id),
            )
            row = cursor.fetchone()
            item = row[0] if row else offer_id
            price = float(data.get("price") or (row[1] if row else 0) or 0)
            order_id = self._new_marketplace_id("order")
            cursor.execute(
                """
                INSERT INTO marketplace_orders (id, order_type, item, price, wallet, status)
                VALUES (?, 'BUY', ?, ?, ?, 'open')
            """,
                (order_id, item, price, wallet),
            )
            conn.commit()
            cursor.execute(
                """
                SELECT id, order_type, item, price, wallet, status, created_at
                FROM marketplace_orders
                WHERE id = ?
            """,
                (order_id,),
            )
            order = self._marketplace_order_row(cursor.fetchone())
            conn.close()
            self.send_json_response({"success": True, "order": order, "order_id": order_id}, status=201)
        except Exception as e:
            self.send_json_response({"success": False, "error": str(e)}, status=400)

    def handle_marketplace_orders(self, parsed):
        query = urllib.parse.parse_qs(parsed.query)
        wallet = query.get("wallet", [None])[0]
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        if wallet:
            cursor.execute(
                """
                SELECT id, order_type, item, price, wallet, status, created_at
                FROM marketplace_orders
                WHERE wallet = ?
                ORDER BY created_at DESC
            """,
                (wallet,),
            )
        else:
            cursor.execute("""
                SELECT id, order_type, item, price, wallet, status, created_at
                FROM marketplace_orders
                ORDER BY created_at DESC
            """)
        orders = [self._marketplace_order_row(row) for row in cursor.fetchall()]
        conn.close()
        self.send_json_response({"orders": orders})

    def handle_marketplace_delete_order(self, path):
        order_id = urllib.parse.unquote(path.rsplit("/", 1)[-1])
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE marketplace_orders SET status = 'cancelled' WHERE id = ?", (order_id,))
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        self.send_json_response({"success": True, "order_id": order_id, "deleted": deleted})

    def handle_marketplace_delete_offer(self, path):
        offer_id = urllib.parse.unquote(path.rsplit("/", 1)[-1])
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE marketplace_offers SET status = 'cancelled' WHERE id = ?", (offer_id,))
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        self.send_json_response({"success": True, "offer_id": offer_id, "deleted": deleted})
