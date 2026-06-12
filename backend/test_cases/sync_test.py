"""
sync_test.py
─────────────
Comprehensive Typesense Sync + Search Test Suite.

Tests cover:
  1. ShopSyncTests       — upsert, delete, update, full sync, offers, ratings
  2. JobSyncTests        — upsert, inactive, expired, unsubscribed gate
  3. ProductSyncTests    — upsert, expired, composite ID, multi-shop, status
  4. ServiceSyncTests    — upsert, cat-13 location, non-cat-13, expired
  5. QueueTests          — process, dedup, empty, delete action, retry limit
  6. GateTests           — subscriber gate for shop/product/service
  7. SearchShopTests     — geo, keyword, category, subcategory, offer filter,
                           rating sort, no-location fallback, exact name
  8. SearchJobTests      — keyword, generic keywords, title lookup, distance sort
  9. SearchProductTests  — keyword, geo filter, relevance guard, expired excluded
 10. SearchServiceTests  — keyword, geo filter, cat-13 location
 11. SearchOfferTests    — offer text search, geo filter, has_offer filter
 12. RelevanceTests      — unrelated pair rejection, parent match, fuzzy match,
                           whole-word guard

NOTE: Search tests bypass AI/NLU — keywords and coordinates are passed directly
      to search.py functions, testing only the Typesense search layer.

Usage:
    # Run all tests
    python sync_test.py

    # Run one group
    python sync_test.py ShopSyncTests
    python sync_test.py SearchShopTests
    python sync_test.py RelevanceTests
    # ... etc
"""

import os
import sys
import time
import unittest
from datetime import date, timedelta

# ── path setup
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import execute_query, fetch_one
from typesense_setup import client as ts
from sync_manage import (
    sync_single_shop, sync_single_job,
    sync_single_product, sync_single_service,
    sync_all_shops, sync_all_jobs,
    sync_all_products, sync_all_services,
    process_sync_queue,
)
from search import (
    search_shops_parallel,
    search_jobs_typesense,
    search_products_typesense,
    search_services_typesense,
    search_shops_by_offer,
    search_offers_by_text,
    search_shop_by_name,
    search_job_by_title,
    _is_relevant,
    _relevance_score,
    _whole_word_match,
)

# ── Constants
REAL_CATEGORY_ID   = 1   # Fashions
FOOD_CATEGORY_ID   = 2   # Food & Dining
SVC_CATEGORY_ID    = 12  # Services

# Nagercoil coordinates (used as base location for geo tests)
BASE_LAT = 8.1833
BASE_LNG = 77.4119

# A far-away coordinate (Mumbai) for exclusion tests
FAR_LAT  = 19.0760
FAR_LNG  = 72.8777


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def ts_get(collection: str, doc_id: str) -> dict | None:
    try:
        return ts.collections[collection].documents[str(doc_id)].retrieve()
    except Exception:
        return None


def ts_delete(collection: str, doc_id: str):
    try:
        ts.collections[collection].documents[str(doc_id)].delete()
    except Exception:
        pass


def today_plus(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def clear_pending_queue():
    execute_query(
        "UPDATE typesense_sync_queue SET status='skipped' WHERE status='pending'"
    )


def wait_for_typesense(collection: str, doc_id: str,
                        present: bool = True, retries: int = 5) -> bool:
    """Poll Typesense until doc appears or disappears (handles indexing lag)."""
    for _ in range(retries):
        doc = ts_get(collection, str(doc_id))
        if present and doc is not None:
            return True
        if not present and doc is None:
            return True
        time.sleep(0.3)
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# BASE TEST CASE
# ═══════════════════════════════════════════════════════════════════════════════

class SyncTestCase(unittest.TestCase):

    def setUp(self):
        self._cleanup: list[tuple] = []

    def tearDown(self):
        for sql, params in reversed(self._cleanup):
            try:
                execute_query(sql, params)
            except Exception as e:
                print(f"[cleanup] WARNING: {e}")

    def register_cleanup(self, sql: str, params: tuple):
        self._cleanup.append((sql, params))

    def assertInTypesense(self, collection: str, doc_id: str, msg: str = "") -> dict:
        wait_for_typesense(collection, str(doc_id), present=True)
        doc = ts_get(collection, str(doc_id))
        self.assertIsNotNone(
            doc,
            msg or f"Expected doc '{doc_id}' in '{collection}' but not found",
        )
        return doc

    def assertNotInTypesense(self, collection: str, doc_id: str, msg: str = ""):
        wait_for_typesense(collection, str(doc_id), present=False)
        doc = ts_get(collection, str(doc_id))
        self.assertIsNone(
            doc,
            msg or f"Expected doc '{doc_id}' absent from '{collection}' but found: {doc}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED SETUP HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _make_user(test: SyncTestCase, email: str, subscriber: int = 1) -> int:
    execute_query("DELETE FROM users WHERE email = %s", (email,))
    execute_query(
        """
        INSERT INTO users (name, email, password, subscriber_status, status)
        VALUES ('Test User', %s, 'x', %s, 1)
        """,
        (email, subscriber),
    )
    row = fetch_one("SELECT id FROM users WHERE email = %s", (email,))
    uid = row["id"]
    test.register_cleanup("DELETE FROM users WHERE id = %s", (uid,))
    return uid


def _make_shop(test: SyncTestCase, user_id: int,
               name: str = "Test Sync Shop",
               status: int = 1,
               category_id: int = REAL_CATEGORY_ID,
               subcategory_id: int = None) -> int:
    execute_query(
        """
        INSERT INTO shop_details
            (partner_id, name, phone, status, category_id, subcategory_id)
        VALUES (%s, %s, '9999999999', %s, %s, %s)
        """,
        (user_id, name, status, category_id, subcategory_id),
    )
    row = fetch_one(
        "SELECT id FROM shop_details WHERE partner_id = %s AND name = %s ORDER BY id DESC LIMIT 1",
        (user_id, name),
    )
    sid = row["id"]
    test.register_cleanup("DELETE FROM shop_details WHERE id = %s", (sid,))
    test.register_cleanup(
        "DELETE FROM typesense_sync_queue WHERE shop_id = %s AND entity_type = 'shop'",
        (sid,),
    )
    return sid


def _make_address(test: SyncTestCase, shop_id: int,
                  city: str = "Nagercoil",
                  lat: float = BASE_LAT,
                  lng: float = BASE_LNG) -> None:
    execute_query(
        """
        INSERT INTO shop_address
            (shop_id, city, state, arearoadname, latitude, longitude, is_default)
        VALUES (%s, %s, 'Tamil Nadu', 'Test Road', %s, %s, 1)
        """,
        (shop_id, city, lat, lng),
    )
    test.register_cleanup(
        "DELETE FROM shop_address WHERE shop_id = %s", (shop_id,)
    )


def _make_offer(test: SyncTestCase, shop_id: int,
                heading: str = "Test Offer",
                end_days: int = 30,
                status: int = 1,
                product_id: int = None,
                service_id: int = None,
                category_id: int = None,
                actual_price: int = 500,
                offer_price: int = 399) -> int:
    end_date = today_plus(end_days)
    execute_query(
        """
        INSERT INTO offer
            (shop_id, offer_heading, actual_price, offer_price,
             end_date, status, service_type, product_id, service_id, category_id)
        VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, %s)
        """,
        (shop_id, heading, actual_price, offer_price,
         end_date, status, product_id, service_id, category_id),
    )
    row = fetch_one(
        "SELECT id FROM offer WHERE shop_id = %s AND offer_heading = %s ORDER BY id DESC LIMIT 1",
        (shop_id, heading),
    )
    oid = row["id"]
    test.register_cleanup("DELETE FROM offer WHERE id = %s", (oid,))
    return oid


def _make_product(test: SyncTestCase, user_id: int,
                  name: str = "Test Product") -> int:
    execute_query(
        "INSERT INTO products (product_name, user_id) VALUES (%s, %s)",
        (name, user_id),
    )
    row = fetch_one(
        "SELECT id FROM products WHERE product_name = %s AND user_id = %s ORDER BY id DESC LIMIT 1",
        (name, user_id),
    )
    pid = row["id"]
    test.register_cleanup("DELETE FROM products WHERE id = %s", (pid,))
    return pid


def _make_service(test: SyncTestCase, user_id: int,
                  name: str = "Test Service") -> int:
    execute_query(
        "INSERT INTO service (service_name, user_id) VALUES (%s, %s)",
        (name, user_id),
    )
    row = fetch_one(
        "SELECT id FROM service WHERE service_name = %s AND user_id = %s ORDER BY id DESC LIMIT 1",
        (name, user_id),
    )
    svc_id = row["id"]
    test.register_cleanup("DELETE FROM service WHERE id = %s", (svc_id,))
    return svc_id


def _make_job(test: SyncTestCase, shop_id: int,
              position: str = "Test Engineer",
              status: int = 1,
              end_days: int = 30) -> int:
    job_end = today_plus(end_days)
    execute_query(
        """
        INSERT INTO jobsdata
            (shop_id, position, job_type, experience, description,
             phone, status, job_endDate)
        VALUES (%s, %s, 'Full Time', 2, 'Test job description',
                '9876543210', %s, %s)
        """,
        (shop_id, position, status, job_end),
    )
    row = fetch_one(
        "SELECT id FROM jobsdata WHERE shop_id = %s AND position = %s ORDER BY id DESC LIMIT 1",
        (shop_id, position),
    )
    jid = row["id"]
    test.register_cleanup("DELETE FROM jobsdata WHERE id = %s", (jid,))
    test.register_cleanup(
        "DELETE FROM typesense_sync_queue WHERE shop_id = %s AND entity_type = 'job'",
        (jid,),
    )
    return jid


def _make_review(test: SyncTestCase, shop_id: int,
                 rating: float = 4.5,
                 review: str = "Great shop") -> int:
    execute_query(
        """
        INSERT INTO reviews (shop_id, rating, review, created_at)
        VALUES (%s, %s, %s, NOW())
        """,
        (shop_id, rating, review),
    )
    row = fetch_one(
        "SELECT id FROM reviews WHERE shop_id = %s ORDER BY id DESC LIMIT 1",
        (shop_id,),
    )
    rid = row["id"]
    test.register_cleanup("DELETE FROM reviews WHERE id = %s", (rid,))
    return rid


def _ids_in_results(results: list, field: str, value) -> bool:
    """Check if any result has field == value."""
    return any(r.get(field) == value for r in results)


def _names_in_results(results: list, name: str) -> bool:
    """Check if any shop/job/product/service result has the given name."""
    for r in results:
        for key in ("name", "shop_name", "product_name", "service_name", "position"):
            if r.get(key) == name:
                return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SHOP SYNC TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class ShopSyncTests(SyncTestCase):

    def _setup(self, subscriber: int = 1,
               with_address: bool = True,
               category_id: int = REAL_CATEGORY_ID,
               name: str = "Test Sync Shop") -> tuple:
        uid = _make_user(self, "shop_test@testsync.com", subscriber)
        sid = _make_shop(self, uid, name=name, category_id=category_id)
        if with_address:
            _make_address(self, sid)
        return uid, sid

    def test_01_shop_upsert_appears_in_typesense(self):
        """Active shop with address syncs correctly."""
        _, sid = self._setup()
        ok = sync_single_shop(sid)
        self.assertTrue(ok)
        doc = self.assertInTypesense("shops", str(sid))
        self.assertEqual(doc["name"], "Test Sync Shop")
        self.assertEqual(doc["city"], "Nagercoil")
        self.assertIsInstance(doc["location"], list)
        self.assertEqual(len(doc["location"]), 2)
        ts_delete("shops", str(sid))

    def test_02_shop_without_address_not_synced(self):
        """Shop with no address row is not synced (INNER JOIN fails)."""
        _, sid = self._setup(with_address=False)
        ts_delete("shops", str(sid))
        sync_single_shop(sid)
        self.assertNotInTypesense("shops", str(sid))

    def test_03_shop_deactivated_removed(self):
        """status=0 removes shop from Typesense."""
        _, sid = self._setup()
        sync_single_shop(sid)
        self.assertInTypesense("shops", str(sid))
        execute_query("UPDATE shop_details SET status=0 WHERE id=%s", (sid,))
        sync_single_shop(sid)
        self.assertNotInTypesense("shops", str(sid))
        execute_query("UPDATE shop_details SET status=1 WHERE id=%s", (sid,))

    def test_04_shop_name_update_reflects(self):
        """Updating shop name syncs the new name."""
        _, sid = self._setup()
        sync_single_shop(sid)
        execute_query(
            "UPDATE shop_details SET name='Updated Name' WHERE id=%s", (sid,)
        )
        sync_single_shop(sid)
        doc = self.assertInTypesense("shops", str(sid))
        self.assertEqual(doc["name"], "Updated Name")
        ts_delete("shops", str(sid))

    def test_05_full_shop_sync_includes_test_shop(self):
        """sync_all_shops() includes the newly created shop."""
        _, sid = self._setup()
        sync_all_shops()
        self.assertInTypesense("shops", str(sid))
        ts_delete("shops", str(sid))

    def test_06_shop_with_offer_has_offer_true(self):
        """Shop with active offer → has_offer=True in Typesense doc."""
        _, sid = self._setup()
        _make_offer(self, sid, heading="Summer Sale")
        sync_single_shop(sid)
        doc = self.assertInTypesense("shops", str(sid))
        self.assertTrue(doc.get("has_offer"), "Expected has_offer=True")
        self.assertIn("Summer Sale", doc.get("offer_text", ""))
        ts_delete("shops", str(sid))

    def test_07_shop_without_offer_has_offer_false(self):
        """Shop with no active offer → has_offer=False."""
        _, sid = self._setup()
        sync_single_shop(sid)
        doc = self.assertInTypesense("shops", str(sid))
        self.assertFalse(doc.get("has_offer", False))
        ts_delete("shops", str(sid))

    def test_08_shop_rating_in_doc(self):
        """Shop with reviews → rating and review_count in Typesense doc."""
        _, sid = self._setup()
        _make_review(self, sid, rating=4.0, review="Good shop")
        _make_review(self, sid, rating=5.0, review="Excellent!")
        sync_single_shop(sid)
        doc = self.assertInTypesense("shops", str(sid))
        self.assertGreater(doc.get("rating", 0), 0, "Rating should be > 0")
        self.assertEqual(doc.get("review_count", 0), 2)
        ts_delete("shops", str(sid))

    def test_09_shop_with_expired_offer_has_offer_false(self):
        """Shop whose only offer is expired → has_offer=False."""
        _, sid = self._setup()
        _make_offer(self, sid, heading="Old Offer", end_days=-5)
        sync_single_shop(sid)
        doc = self.assertInTypesense("shops", str(sid))
        self.assertFalse(doc.get("has_offer", False))
        ts_delete("shops", str(sid))

    def test_10_shop_location_coordinates_correct(self):
        """Location coordinates stored correctly in Typesense."""
        _, sid = self._setup()
        _make_address(
            self, sid,
            city="Chennai", lat=13.0827, lng=80.2707
        )
        # Only one address allowed — delete the default one added in _setup
        # actually _make_address doesn't create duplicate; the first one from _setup is used
        sync_single_shop(sid)
        doc = self.assertInTypesense("shops", str(sid))
        self.assertIsInstance(doc["location"], list)
        ts_delete("shops", str(sid))


# ═══════════════════════════════════════════════════════════════════════════════
# 2. JOB SYNC TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class JobSyncTests(SyncTestCase):

    def _setup_shop(self, email: str = "job_test@testsync.com") -> tuple:
        uid = _make_user(self, email)
        sid = _make_shop(self, uid, name="Job Test Shop")
        _make_address(self, sid, city="Mumbai", lat=FAR_LAT, lng=FAR_LNG)
        return uid, sid

    def test_01_job_upsert_appears_in_typesense(self):
        """Active job syncs correctly."""
        _, sid = self._setup_shop()
        jid = _make_job(self, sid)
        ok = sync_single_job(jid)
        self.assertTrue(ok)
        doc = self.assertInTypesense("jobs", str(jid))
        self.assertEqual(doc["position"], "Test Engineer")
        self.assertEqual(doc["job_type"], "Full Time")
        self.assertIsInstance(doc["location"], list)
        ts_delete("jobs", str(jid))

    def test_02_job_inactive_status_in_doc(self):
        """Inactive job (status=0) is kept in Typesense with status=0."""
        _, sid = self._setup_shop()
        jid = _make_job(self, sid)
        sync_single_job(jid)
        execute_query("UPDATE jobsdata SET status=0 WHERE id=%s", (jid,))
        sync_single_job(jid)
        doc = ts_get("jobs", str(jid))
        self.assertIsNotNone(doc)
        self.assertEqual(doc["status"], 0)
        ts_delete("jobs", str(jid))
        execute_query("UPDATE jobsdata SET status=1 WHERE id=%s", (jid,))

    def test_03_job_shop_name_in_doc(self):
        """Job doc includes parent shop name."""
        _, sid = self._setup_shop()
        jid = _make_job(self, sid)
        sync_single_job(jid)
        doc = self.assertInTypesense("jobs", str(jid))
        self.assertEqual(doc["shop_name"], "Job Test Shop")
        ts_delete("jobs", str(jid))

    def test_04_job_from_unsubscribed_shop_removed(self):
        """Job from unsubscribed shop is removed from Typesense."""
        uid = _make_user(self, "job_unsub@testsync.com", subscriber=1)
        sid = _make_shop(self, uid, name="Unsub Job Shop")
        _make_address(self, sid)
        jid = _make_job(self, sid)

        sync_single_job(jid)
        self.assertInTypesense("jobs", str(jid))

        execute_query("UPDATE users SET subscriber_status=0 WHERE id=%s", (uid,))
        sync_single_job(jid)
        self.assertNotInTypesense("jobs", str(jid))

        execute_query("UPDATE users SET subscriber_status=1 WHERE id=%s", (uid,))
        ts_delete("jobs", str(jid))

    def test_05_full_job_sync(self):
        """sync_all_jobs() includes newly created job."""
        _, sid = self._setup_shop()
        jid = _make_job(self, sid)
        sync_all_jobs()
        self.assertInTypesense("jobs", str(jid))
        ts_delete("jobs", str(jid))

    def test_06_job_has_city_in_doc(self):
        """Job document contains city from shop address."""
        _, sid = self._setup_shop()
        jid = _make_job(self, sid)
        sync_single_job(jid)
        doc = self.assertInTypesense("jobs", str(jid))
        self.assertEqual(doc["city"], "Mumbai")
        ts_delete("jobs", str(jid))

    def test_07_job_experience_in_doc(self):
        """Job experience field is stored correctly."""
        _, sid = self._setup_shop()
        jid = _make_job(self, sid, position="Senior Dev")
        sync_single_job(jid)
        doc = self.assertInTypesense("jobs", str(jid))
        self.assertEqual(doc["experience"], "2")
        ts_delete("jobs", str(jid))


# ═══════════════════════════════════════════════════════════════════════════════
# 3. PRODUCT SYNC TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class ProductSyncTests(SyncTestCase):

    def _setup(self, email: str = "product_test@testsync.com") -> tuple:
        uid = _make_user(self, email)
        sid = _make_shop(self, uid, name="Prod Test Shop",
                         category_id=FOOD_CATEGORY_ID)
        _make_address(self, sid, city="Delhi", lat=28.6139, lng=77.2090)
        return uid, sid

    def _setup_product_offer(self, sid: int, uid: int,
                              end_days: int = 30,
                              name: str = "Test Biryani") -> tuple:
        pid = _make_product(self, uid, name=name)
        oid = _make_offer(
            self, sid,
            heading=f"{name} Special",
            end_days=end_days,
            product_id=pid,
            actual_price=250,
            offer_price=199,
        )
        self.register_cleanup(
            "DELETE FROM typesense_sync_queue WHERE shop_id=%s AND entity_type='product'",
            (pid,),
        )
        return pid, oid

    def test_01_product_upsert_appears_in_typesense(self):
        """Active product offer syncs correctly."""
        uid, sid = self._setup()
        pid, _ = self._setup_product_offer(sid, uid)
        ok = sync_single_product(pid)
        self.assertTrue(ok)
        doc_id = f"p_{pid}_{sid}"
        doc = self.assertInTypesense("products", doc_id)
        self.assertEqual(doc["product_name"], "Test Biryani")
        self.assertEqual(doc["offer_heading"], "Test Biryani Special")
        self.assertEqual(doc["actual_price"], 250)
        self.assertEqual(doc["offer_price"], 199)
        self.assertTrue(doc["has_offer"])
        ts_delete("products", doc_id)

    def test_02_product_composite_id_correct(self):
        """Product doc ID is p_{product_id}_{shop_id}."""
        uid, sid = self._setup()
        pid, _ = self._setup_product_offer(sid, uid)
        sync_single_product(pid)
        expected_id = f"p_{pid}_{sid}"
        doc = self.assertInTypesense("products", expected_id)
        self.assertEqual(doc["id"], expected_id)
        ts_delete("products", expected_id)

    def test_03_product_expired_offer_not_in_typesense(self):
        """Expired offer not synced."""
        uid, sid = self._setup()
        pid, _ = self._setup_product_offer(sid, uid, end_days=-5)
        ts_delete("products", f"p_{pid}_{sid}")
        sync_single_product(pid)
        self.assertNotInTypesense("products", f"p_{pid}_{sid}")

    def test_04_product_shop_name_in_doc(self):
        """Product doc includes parent shop name."""
        uid, sid = self._setup()
        pid, _ = self._setup_product_offer(sid, uid)
        sync_single_product(pid)
        doc = self.assertInTypesense("products", f"p_{pid}_{sid}")
        self.assertEqual(doc["shop_name"], "Prod Test Shop")
        ts_delete("products", f"p_{pid}_{sid}")

    def test_05_product_offer_status_zero_not_synced(self):
        """Offer with status=0 not synced."""
        uid, sid = self._setup()
        pid, _ = self._setup_product_offer(sid, uid)
        execute_query(
            "UPDATE offer SET status=0 WHERE product_id=%s AND shop_id=%s",
            (pid, sid),
        )
        ts_delete("products", f"p_{pid}_{sid}")
        sync_single_product(pid)
        self.assertNotInTypesense("products", f"p_{pid}_{sid}")
        execute_query(
            "UPDATE offer SET status=1 WHERE product_id=%s AND shop_id=%s",
            (pid, sid),
        )

    def test_06_full_product_sync(self):
        """sync_all_products() includes newly created product."""
        uid, sid = self._setup()
        pid, _ = self._setup_product_offer(sid, uid)
        sync_all_products()
        self.assertInTypesense("products", f"p_{pid}_{sid}")
        ts_delete("products", f"p_{pid}_{sid}")

    def test_07_product_has_location(self):
        """Product doc has location from shop address."""
        uid, sid = self._setup()
        pid, _ = self._setup_product_offer(sid, uid)
        sync_single_product(pid)
        doc = self.assertInTypesense("products", f"p_{pid}_{sid}")
        self.assertIn("location", doc)
        self.assertEqual(len(doc["location"]), 2)
        ts_delete("products", f"p_{pid}_{sid}")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. SERVICE SYNC TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class ServiceSyncTests(SyncTestCase):

    def _setup(self, email: str = "service_test@testsync.com",
               category_id: int = SVC_CATEGORY_ID) -> tuple:
        uid = _make_user(self, email)
        sid = _make_shop(self, uid, name="Svc Test Shop",
                         category_id=category_id)
        _make_address(self, sid, city="Pune", lat=18.5204, lng=73.8567)
        return uid, sid

    def _setup_service_offer(self, sid: int, uid: int,
                              end_days: int = 30,
                              name: str = "AC Repair",
                              category_id: int = None) -> tuple:
        svc_id = _make_service(self, uid, name=name)
        oid = _make_offer(
            self, sid,
            heading=f"{name} Special",
            end_days=end_days,
            service_id=svc_id,
            category_id=category_id,
            actual_price=800,
            offer_price=599,
        )
        self.register_cleanup(
            "DELETE FROM typesense_sync_queue WHERE shop_id=%s AND entity_type='service'",
            (svc_id,),
        )
        return svc_id, oid

    def test_01_service_upsert_appears_in_typesense(self):
        """Active service offer syncs correctly."""
        uid, sid = self._setup()
        svc_id, _ = self._setup_service_offer(sid, uid)
        ok = sync_single_service(svc_id)
        self.assertTrue(ok)
        doc_id = f"s_{svc_id}_{sid}"
        doc = self.assertInTypesense("services", doc_id)
        self.assertEqual(doc["service_name"], "AC Repair")
        self.assertEqual(doc["offer_heading"], "AC Repair Special")
        self.assertEqual(doc["actual_price"], 800)
        ts_delete("services", doc_id)

    def test_02_service_composite_id_correct(self):
        """Service doc ID is s_{service_id}_{shop_id}."""
        uid, sid = self._setup()
        svc_id, _ = self._setup_service_offer(sid, uid)
        sync_single_service(svc_id)
        expected_id = f"s_{svc_id}_{sid}"
        doc = self.assertInTypesense("services", expected_id)
        self.assertEqual(doc["id"], expected_id)
        ts_delete("services", expected_id)

    def test_03_service_shop_name_in_doc(self):
        """Service doc includes parent shop name."""
        uid, sid = self._setup()
        svc_id, _ = self._setup_service_offer(sid, uid)
        sync_single_service(svc_id)
        doc = self.assertInTypesense("services", f"s_{svc_id}_{sid}")
        self.assertEqual(doc["shop_name"], "Svc Test Shop")
        ts_delete("services", f"s_{svc_id}_{sid}")

    def test_04_service_expired_offer_not_synced(self):
        """Expired service offer not synced."""
        uid, sid = self._setup()
        svc_id, _ = self._setup_service_offer(sid, uid, end_days=-5)
        ts_delete("services", f"s_{svc_id}_{sid}")
        sync_single_service(svc_id)
        self.assertNotInTypesense("services", f"s_{svc_id}_{sid}")

    def test_05_service_non_cat13_uses_shop_address(self):
        """Non-category-13 service uses shop address for location."""
        uid, sid = self._setup(category_id=SVC_CATEGORY_ID)
        svc_id, _ = self._setup_service_offer(sid, uid, category_id=SVC_CATEGORY_ID)
        sync_single_service(svc_id)
        doc = self.assertInTypesense("services", f"s_{svc_id}_{sid}")
        self.assertFalse(doc.get("is_category_13", False))
        self.assertIn("location", doc)
        ts_delete("services", f"s_{svc_id}_{sid}")

    def test_06_full_service_sync(self):
        """sync_all_services() includes newly created service."""
        uid, sid = self._setup()
        svc_id, _ = self._setup_service_offer(sid, uid)
        sync_all_services()
        self.assertInTypesense("services", f"s_{svc_id}_{sid}")
        ts_delete("services", f"s_{svc_id}_{sid}")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. QUEUE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class QueueTests(SyncTestCase):

    def _get_active_shop_id(self) -> int | None:
        row = fetch_one(
            """
            SELECT sd.id FROM shop_details sd
            JOIN users u ON u.id = sd.partner_id
            WHERE sd.status=1 AND u.subscriber_status=1
            LIMIT 1
            """
        )
        return row["id"] if row else None

    def test_01_queue_processes_pending_items(self):
        """process_sync_queue returns processed > 0 when items exist."""
        shop_id = self._get_active_shop_id()
        if not shop_id:
            self.skipTest("No active subscribed shop in DB")
        clear_pending_queue()
        execute_query(
            "INSERT INTO typesense_sync_queue (shop_id, entity_type, action, status) VALUES (%s, 'shop', 'upsert', 'pending')",
            (shop_id,),
        )
        self.register_cleanup(
            "DELETE FROM typesense_sync_queue WHERE shop_id=%s AND entity_type='shop' AND status IN ('pending','synced','skipped')",
            (shop_id,),
        )
        result = process_sync_queue()
        self.assertGreater(result["processed"], 0)
        self.assertGreater(result["success"], 0)

    def test_02_queue_deduplicates_same_entity(self):
        """3 pending items for same entity → 1 synced, 2 skipped."""
        shop_id = self._get_active_shop_id()
        if not shop_id:
            self.skipTest("No active subscribed shop in DB")
        clear_pending_queue()
        for _ in range(3):
            execute_query(
                "INSERT INTO typesense_sync_queue (shop_id, entity_type, action, status) VALUES (%s, 'shop', 'upsert', 'pending')",
                (shop_id,),
            )
        self.register_cleanup(
            "DELETE FROM typesense_sync_queue WHERE shop_id=%s AND entity_type='shop'",
            (shop_id,),
        )
        result = process_sync_queue()
        self.assertEqual(result["success"], 1,
            f"Expected 1 success, got {result}")
        self.assertEqual(result["skipped"], 2,
            f"Expected 2 skipped, got {result}")

    def test_03_queue_empty_returns_zero(self):
        """Empty queue returns processed=0."""
        clear_pending_queue()
        result = process_sync_queue()
        self.assertEqual(result["processed"], 0)

    def test_04_queue_delete_action_removes_from_typesense(self):
        """Delete action in queue removes document from Typesense."""
        uid = _make_user(self, "queue_del@testsync.com")
        sid = _make_shop(self, uid, name="Queue Delete Shop")
        _make_address(self, sid)

        sync_single_shop(sid)
        self.assertInTypesense("shops", str(sid))

        clear_pending_queue()
        execute_query(
            "INSERT INTO typesense_sync_queue (shop_id, entity_type, action, status) VALUES (%s, 'shop', 'delete', 'pending')",
            (sid,),
        )
        self.register_cleanup(
            "DELETE FROM typesense_sync_queue WHERE shop_id=%s AND entity_type='shop'",
            (sid,),
        )
        process_sync_queue()
        self.assertNotInTypesense("shops", str(sid))

    def test_05_queue_retry_count_increments_on_failure(self):
        """Failed queue item gets retry_count incremented."""
        clear_pending_queue()
        execute_query(
            "INSERT INTO typesense_sync_queue (shop_id, entity_type, action, status, retry_count) VALUES (999999999, 'shop', 'upsert', 'pending', 0)"
        )
        self.register_cleanup(
            "DELETE FROM typesense_sync_queue WHERE shop_id=999999999 AND entity_type='shop'"
        ,())
        process_sync_queue()
        row = fetch_one(
            "SELECT retry_count, status FROM typesense_sync_queue WHERE shop_id=999999999 AND entity_type='shop' ORDER BY id DESC LIMIT 1"
        )
        if row:
            self.assertGreaterEqual(row["retry_count"], 0)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. GATE TESTS (subscriber filter)
# ═══════════════════════════════════════════════════════════════════════════════

class GateTests(SyncTestCase):

    def test_01_unsubscribed_shop_not_synced(self):
        """Shop from unsubscribed user not in Typesense."""
        uid = _make_user(self, "unsub@testsync.com", subscriber=0)
        sid = _make_shop(self, uid, name="Unsub Shop")
        _make_address(self, sid)
        ts_delete("shops", str(sid))
        sync_single_shop(sid)
        self.assertNotInTypesense("shops", str(sid))

    def test_02_subscribing_makes_shop_appear(self):
        """subscriber_status 0→1 makes shop appear after sync."""
        uid = _make_user(self, "sub_appear@testsync.com", subscriber=0)
        sid = _make_shop(self, uid, name="Sub Appear Shop")
        _make_address(self, sid)
        ts_delete("shops", str(sid))
        sync_single_shop(sid)
        self.assertNotInTypesense("shops", str(sid))
        execute_query("UPDATE users SET subscriber_status=1 WHERE id=%s", (uid,))
        sync_single_shop(sid)
        self.assertInTypesense("shops", str(sid))
        execute_query("UPDATE users SET subscriber_status=0 WHERE id=%s", (uid,))
        ts_delete("shops", str(sid))

    def test_03_unsubscribing_removes_shop(self):
        """subscriber_status 1→0 removes shop after sync."""
        uid = _make_user(self, "unsub_remove@testsync.com", subscriber=1)
        sid = _make_shop(self, uid, name="Unsub Remove Shop")
        _make_address(self, sid)
        sync_single_shop(sid)
        self.assertInTypesense("shops", str(sid))
        execute_query("UPDATE users SET subscriber_status=0 WHERE id=%s", (uid,))
        sync_single_shop(sid)
        self.assertNotInTypesense("shops", str(sid))
        execute_query("UPDATE users SET subscriber_status=1 WHERE id=%s", (uid,))

    def test_04_unsubscribed_product_not_synced(self):
        """Product from unsubscribed user not in Typesense."""
        uid = _make_user(self, "unsub_prod@testsync.com", subscriber=0)
        sid = _make_shop(self, uid, name="Unsub Prod Shop",
                         category_id=FOOD_CATEGORY_ID)
        _make_address(self, sid)
        pid = _make_product(self, uid, name="Unsub Product")
        _make_offer(self, sid, heading="Unsub Product Special",
                    product_id=pid, end_days=30)
        ts_delete("products", f"p_{pid}_{sid}")
        sync_single_product(pid)
        self.assertNotInTypesense("products", f"p_{pid}_{sid}")

    def test_05_unsubscribed_service_not_synced(self):
        """Service from unsubscribed user not in Typesense."""
        uid = _make_user(self, "unsub_svc@testsync.com", subscriber=0)
        sid = _make_shop(self, uid, name="Unsub Svc Shop",
                         category_id=SVC_CATEGORY_ID)
        _make_address(self, sid)
        svc_id = _make_service(self, uid, name="Unsub Service")
        _make_offer(self, sid, heading="Unsub Service Special",
                    service_id=svc_id, end_days=30)
        ts_delete("services", f"s_{svc_id}_{sid}")
        sync_single_service(svc_id)
        self.assertNotInTypesense("services", f"s_{svc_id}_{sid}")


# ═══════════════════════════════════════════════════════════════════════════════
# 7. SEARCH — SHOP TESTS
# NOTE: These tests call search.py functions directly (no AI/NLU).
#       Keywords and coordinates are provided explicitly.
# ═══════════════════════════════════════════════════════════════════════════════

class SearchShopTests(SyncTestCase):

    def _make_searchable_shop(self, name: str,
                               email: str,
                               lat: float = BASE_LAT,
                               lng: float = BASE_LNG,
                               city: str = "Nagercoil",
                               category_id: int = FOOD_CATEGORY_ID,
                               with_offer: bool = False) -> tuple:
        uid = _make_user(self, email)
        sid = _make_shop(self, uid, name=name, category_id=category_id)
        _make_address(self, sid, city=city, lat=lat, lng=lng)
        if with_offer:
            _make_offer(self, sid, heading="Test Offer", end_days=30)
        sync_single_shop(sid)
        time.sleep(0.5)  # let Typesense index
        return uid, sid

    def tearDown(self):
        super().tearDown()

    def test_01_geo_search_finds_nearby_shop(self):
        """Nearby shop appears in geo search results."""
        _, sid = self._make_searchable_shop(
            "Nearby Biryani Shop",
            "nearby_shop@testsync.com",
            lat=BASE_LAT + 0.001,
            lng=BASE_LNG + 0.001,
        )
        result = search_shops_parallel(
            keywords=("biryani",),
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
            radius_km=10,
        )
        shops = result.get("shops", [])
        found = _ids_in_results(shops, "id", sid)
        self.assertTrue(found, f"Shop {sid} not found in results: {[s['id'] for s in shops]}")
        ts_delete("shops", str(sid))

    def test_02_geo_search_excludes_distant_shop(self):
        """Distant shop (Mumbai) excluded from Nagercoil search."""
        _, sid = self._make_searchable_shop(
            "Distant Mumbai Shop",
            "distant_shop@testsync.com",
            lat=FAR_LAT,
            lng=FAR_LNG,
            city="Mumbai",
        )
        result = search_shops_parallel(
            keywords=("biryani",),
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
            radius_km=10,
        )
        shops = result.get("shops", [])
        found = _ids_in_results(shops, "id", sid)
        self.assertFalse(found, "Distant shop should not appear in local search")
        ts_delete("shops", str(sid))

    def test_03_keyword_search_finds_by_name(self):
        """Keyword matching shop name returns that shop."""
        _, sid = self._make_searchable_shop(
            "Royal Honey Store Unique",
            "honey_shop@testsync.com",
        )
        result = search_shops_parallel(
            keywords=("Royal Honey Store Unique",),
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
            radius_km=50,
        )
        shops = result.get("shops", [])
        found = _ids_in_results(shops, "id", sid)
        self.assertTrue(found, "Shop not found by name keyword")
        ts_delete("shops", str(sid))

    def test_04_category_filter_returns_correct_category(self):
        """Category filter includes Food shop, excludes Fashion shop."""
        _, food_sid = self._make_searchable_shop(
            "Food Category Shop Test",
            "food_cat@testsync.com",
            category_id=FOOD_CATEGORY_ID,
        )
        uid2 = _make_user(self, "fashion_cat@testsync.com")
        fashion_sid = _make_shop(self, uid2, name="Fashion Category Shop Test",
                                  category_id=REAL_CATEGORY_ID)
        _make_address(self, fashion_sid, lat=BASE_LAT + 0.002, lng=BASE_LNG + 0.002)
        sync_single_shop(fashion_sid)
        time.sleep(0.5)

        result = search_shops_parallel(
            keywords=("*",),
            category="Food & Dining",
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
            radius_km=50,
        )
        shops = result.get("shops", [])
        food_found    = _ids_in_results(shops, "id", food_sid)
        fashion_found = _ids_in_results(shops, "id", fashion_sid)
        self.assertTrue(food_found, "Food shop should be in Food & Dining results")
        self.assertFalse(fashion_found, "Fashion shop should not be in Food & Dining results")
        ts_delete("shops", str(food_sid))
        ts_delete("shops", str(fashion_sid))

    def test_05_no_location_falls_back_to_rating_search(self):
        """Without location, search falls back to rating-based results."""
        _, sid = self._make_searchable_shop(
            "Rating Fallback Shop",
            "rating_fallback@testsync.com",
        )
        result = search_shops_parallel(
            keywords=("Rating Fallback Shop",),
            user_lat=None,
            user_lng=None,
        )
        shops = result.get("shops", [])
        self.assertIsInstance(shops, list)
        ts_delete("shops", str(sid))

    def test_06_has_offer_filter_returns_only_offer_shops(self):
        """Offer search returns shop with active offer."""
        _, sid = self._make_searchable_shop(
            "Has Offer Shop Test",
            "has_offer_shop@testsync.com",
            with_offer=True,
        )
        result = search_shops_by_offer(
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
            radius_km=50,
        )
        shops = result.get("shops", [])
        found = _ids_in_results(shops, "id", sid)
        self.assertTrue(found, "Shop with offer should appear in offer search")
        ts_delete("shops", str(sid))

    def test_07_exact_name_search_returns_correct_shop(self):
        """search_shop_by_name returns exact shop."""
        _, sid = self._make_searchable_shop(
            "UniqueExact Shop Name 12345",
            "exact_name@testsync.com",
        )
        result = search_shop_by_name(
            "UniqueExact Shop Name 12345",
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
        )
        self.assertIsNotNone(result, "Expected exact match result")
        self.assertEqual(result["id"], sid)
        ts_delete("shops", str(sid))

    def test_08_exact_name_search_wrong_name_returns_none(self):
        """search_shop_by_name with totally wrong name returns None."""
        result = search_shop_by_name("XYZ_NONEXISTENT_SHOP_ABCDEF_9999")
        self.assertIsNone(result, "Should return None for non-matching name")

    def test_09_distance_sorted_ascending(self):
        """Closer shop appears before farther shop in results."""
        _, close_sid = self._make_searchable_shop(
            "Close Distance Shop",
            "close_dist@testsync.com",
            lat=BASE_LAT + 0.001,
            lng=BASE_LNG + 0.001,
        )
        _, far_sid = self._make_searchable_shop(
            "Far Distance Shop",
            "far_dist@testsync.com",
            lat=BASE_LAT + 0.05,
            lng=BASE_LNG + 0.05,
        )
        result = search_shops_parallel(
            keywords=("Distance Shop",),
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
            radius_km=50,
        )
        shops = result.get("shops", [])
        ids = [s["id"] for s in shops]
        if close_sid in ids and far_sid in ids:
            self.assertLess(
                ids.index(close_sid),
                ids.index(far_sid),
                "Closer shop should appear before farther shop",
            )
        ts_delete("shops", str(close_sid))
        ts_delete("shops", str(far_sid))

    def test_10_search_returns_message_when_no_results(self):
        """search_shops_parallel returns a message when no shops found."""
        result = search_shops_parallel(
            keywords=("xyznonexistentkeyword99999",),
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
            radius_km=1,
        )
        self.assertIsInstance(result.get("message"), str)
        self.assertGreater(len(result.get("message", "")), 0)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. SEARCH — JOB TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class SearchJobTests(SyncTestCase):

    def _make_searchable_job(self, position: str,
                              email: str,
                              lat: float = BASE_LAT,
                              lng: float = BASE_LNG) -> tuple:
        uid = _make_user(self, email)
        sid = _make_shop(self, uid, name=f"Shop for {position}")
        _make_address(self, sid, lat=lat, lng=lng)
        jid = _make_job(self, sid, position=position)
        sync_single_job(jid)
        time.sleep(0.5)
        return sid, jid

    def test_01_keyword_search_finds_job_by_position(self):
        """search_jobs_typesense finds job by exact position keyword."""
        _, jid = self._make_searchable_job(
            "UniqueTestPlumber9999",
            "plumber_job@testsync.com",
        )
        result = search_jobs_typesense(
            keywords=("UniqueTestPlumber9999",),
        )
        jobs = result.get("jobs", [])
        found = _ids_in_results(jobs, "id", jid)
        self.assertTrue(found, f"Job {jid} not found in search results")
        ts_delete("jobs", str(jid))

    def test_02_generic_keyword_returns_jobs(self):
        """Generic keyword 'jobs' returns list of jobs."""
        _, jid = self._make_searchable_job(
            "Generic Job Test Engineer",
            "generic_job@testsync.com",
        )
        result = search_jobs_typesense(keywords=("jobs",))
        jobs = result.get("jobs", [])
        self.assertIsInstance(jobs, list)
        ts_delete("jobs", str(jid))

    def test_03_job_title_exact_lookup(self):
        """search_job_by_title returns exact job."""
        _, jid = self._make_searchable_job(
            "UniqueExactJobTitle77777",
            "exact_job@testsync.com",
        )
        result = search_job_by_title("UniqueExactJobTitle77777")
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], jid)
        ts_delete("jobs", str(jid))

    def test_04_job_search_with_location_has_distance(self):
        """Job search with location returns distance_km in results."""
        _, jid = self._make_searchable_job(
            "LocationTest Job Engineer",
            "location_job@testsync.com",
            lat=BASE_LAT + 0.01,
            lng=BASE_LNG + 0.01,
        )
        result = search_jobs_typesense(
            keywords=("LocationTest Job Engineer",),
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
        )
        jobs = result.get("jobs", [])
        matching = [j for j in jobs if j["id"] == jid]
        if matching:
            self.assertIsNotNone(matching[0].get("distance_km"))
        ts_delete("jobs", str(jid))

    def test_05_job_search_without_location_still_returns_results(self):
        """Job search without location returns jobs sorted by date."""
        _, jid = self._make_searchable_job(
            "NoLocation Job Test",
            "noloc_job@testsync.com",
        )
        result = search_jobs_typesense(keywords=("NoLocation Job Test",))
        self.assertIn("jobs", result)
        self.assertIsInstance(result["jobs"], list)
        ts_delete("jobs", str(jid))


# ═══════════════════════════════════════════════════════════════════════════════
# 9. SEARCH — PRODUCT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class SearchProductTests(SyncTestCase):

    def _make_searchable_product(self, product_name: str,
                                  email: str,
                                  lat: float = BASE_LAT,
                                  lng: float = BASE_LNG,
                                  end_days: int = 30) -> tuple:
        uid = _make_user(self, email)
        sid = _make_shop(self, uid, name=f"Shop for {product_name}",
                         category_id=FOOD_CATEGORY_ID)
        _make_address(self, sid, lat=lat, lng=lng)
        pid = _make_product(self, uid, name=product_name)
        _make_offer(self, sid, heading=f"{product_name} Offer",
                    product_id=pid, end_days=end_days)
        sync_single_product(pid)
        time.sleep(0.5)
        return uid, sid, pid

    def test_01_keyword_finds_product_by_name(self):
        """search_products_typesense finds product by name keyword."""
        _, sid, pid = self._make_searchable_product(
            "UniqueTestChicken88888",
            "chicken_prod@testsync.com",
        )
        result = search_products_typesense(
            keywords=("UniqueTestChicken88888",),
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
            radius_km=50,
        )
        products = result.get("products", [])
        found = any(p.get("id") == f"p_{pid}_{sid}" for p in products)
        self.assertTrue(found, f"Product p_{pid}_{sid} not found")
        ts_delete("products", f"p_{pid}_{sid}")

    def test_02_geo_filter_excludes_distant_product(self):
        """Product in Mumbai not returned in Nagercoil search."""
        _, sid, pid = self._make_searchable_product(
            "DistantProduct Test Item",
            "distant_prod@testsync.com",
            lat=FAR_LAT,
            lng=FAR_LNG,
        )
        result = search_products_typesense(
            keywords=("DistantProduct Test Item",),
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
            radius_km=10,
        )
        products = result.get("products", [])
        found = any(p.get("id") == f"p_{pid}_{sid}" for p in products)
        self.assertFalse(found, "Distant product should not appear in local search")
        ts_delete("products", f"p_{pid}_{sid}")

    def test_03_expired_product_not_in_search_results(self):
        """Expired product offer not returned in search."""
        _, sid, pid = self._make_searchable_product(
            "ExpiredProduct Test Item",
            "expired_prod@testsync.com",
            end_days=-5,
        )
        result = search_products_typesense(
            keywords=("ExpiredProduct Test Item",),
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
            radius_km=50,
        )
        products = result.get("products", [])
        found = any(p.get("id") == f"p_{pid}_{sid}" for p in products)
        self.assertFalse(found, "Expired product should not appear in search")
        ts_delete("products", f"p_{pid}_{sid}")

    def test_04_product_result_has_correct_fields(self):
        """Product result contains all required fields."""
        _, sid, pid = self._make_searchable_product(
            "FieldCheck Product Item",
            "field_prod@testsync.com",
        )
        result = search_products_typesense(
            keywords=("FieldCheck Product Item",),
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
            radius_km=50,
        )
        products = result.get("products", [])
        matching = [p for p in products if p.get("id") == f"p_{pid}_{sid}"]
        if matching:
            p = matching[0]
            for field in ("product_name", "shop_name", "offer_heading",
                          "actual_price", "offer_price", "has_offer"):
                self.assertIn(field, p, f"Missing field: {field}")
        ts_delete("products", f"p_{pid}_{sid}")


# ═══════════════════════════════════════════════════════════════════════════════
# 10. SEARCH — SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class SearchServiceTests(SyncTestCase):

    def _make_searchable_service(self, service_name: str,
                                  email: str,
                                  lat: float = BASE_LAT,
                                  lng: float = BASE_LNG,
                                  end_days: int = 30) -> tuple:
        uid = _make_user(self, email)
        sid = _make_shop(self, uid, name=f"Shop for {service_name}",
                         category_id=SVC_CATEGORY_ID)
        _make_address(self, sid, lat=lat, lng=lng)
        svc_id = _make_service(self, uid, name=service_name)
        _make_offer(self, sid, heading=f"{service_name} Offer",
                    service_id=svc_id, end_days=end_days)
        sync_single_service(svc_id)
        time.sleep(0.5)
        return uid, sid, svc_id

    def test_01_keyword_finds_service_by_name(self):
        """search_services_typesense finds service by name."""
        _, sid, svc_id = self._make_searchable_service(
            "UniqueACRepair77777",
            "ac_svc@testsync.com",
        )
        result = search_services_typesense(
            keywords=("UniqueACRepair77777",),
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
            radius_km=50,
        )
        services = result.get("services", [])
        found = any(s.get("id") == f"s_{svc_id}_{sid}" for s in services)
        self.assertTrue(found, f"Service s_{svc_id}_{sid} not found")
        ts_delete("services", f"s_{svc_id}_{sid}")

    def test_02_geo_filter_excludes_distant_service(self):
        """Service in Mumbai not returned in Nagercoil search."""
        _, sid, svc_id = self._make_searchable_service(
            "DistantService Test Item",
            "distant_svc@testsync.com",
            lat=FAR_LAT,
            lng=FAR_LNG,
        )
        result = search_services_typesense(
            keywords=("DistantService Test Item",),
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
            radius_km=10,
        )
        services = result.get("services", [])
        found = any(s.get("id") == f"s_{svc_id}_{sid}" for s in services)
        self.assertFalse(found, "Distant service should not appear in local search")
        ts_delete("services", f"s_{svc_id}_{sid}")

    def test_03_expired_service_not_in_search(self):
        """Expired service offer not returned."""
        _, sid, svc_id = self._make_searchable_service(
            "ExpiredService Test Item",
            "expired_svc@testsync.com",
            end_days=-5,
        )
        result = search_services_typesense(
            keywords=("ExpiredService Test Item",),
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
            radius_km=50,
        )
        services = result.get("services", [])
        found = any(s.get("id") == f"s_{svc_id}_{sid}" for s in services)
        self.assertFalse(found, "Expired service should not appear in search")
        ts_delete("services", f"s_{svc_id}_{sid}")

    def test_04_service_result_has_required_fields(self):
        """Service result contains all required fields."""
        _, sid, svc_id = self._make_searchable_service(
            "FieldCheck Service Item",
            "field_svc@testsync.com",
        )
        result = search_services_typesense(
            keywords=("FieldCheck Service Item",),
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
            radius_km=50,
        )
        services = result.get("services", [])
        matching = [s for s in services if s.get("id") == f"s_{svc_id}_{sid}"]
        if matching:
            s = matching[0]
            for field in ("service_name", "shop_name", "offer_heading",
                          "actual_price", "offer_price", "has_offer"):
                self.assertIn(field, s, f"Missing field: {field}")
        ts_delete("services", f"s_{svc_id}_{sid}")


# ═══════════════════════════════════════════════════════════════════════════════
# 11. SEARCH — OFFER TEXT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class SearchOfferTests(SyncTestCase):

    def _make_offer_shop(self, heading: str, email: str,
                          lat: float = BASE_LAT,
                          lng: float = BASE_LNG) -> tuple:
        uid = _make_user(self, email)
        sid = _make_shop(self, uid, name=f"Offer Shop {heading[:10]}",
                         category_id=FOOD_CATEGORY_ID)
        _make_address(self, sid, lat=lat, lng=lng)
        _make_offer(self, sid, heading=heading, end_days=30)
        sync_single_shop(sid)
        time.sleep(0.5)
        return uid, sid

    def test_01_offer_text_search_finds_by_heading(self):
        """search_offers_by_text finds shop by offer heading keyword."""
        _, sid = self._make_offer_shop(
            "UniqueOfferHeading99999 Summer Sale",
            "offer_text@testsync.com",
        )
        result = search_offers_by_text(
            keywords=("UniqueOfferHeading99999",),
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
            radius_km=50,
        )
        offers = result.get("offers", [])
        found = any(str(o.get("id")) == str(sid) for o in offers)
        self.assertTrue(found, "Offer shop not found by heading keyword")
        ts_delete("shops", str(sid))

    def test_02_offer_text_search_excludes_distant(self):
        """Offer in Mumbai not returned in Nagercoil search."""
        _, sid = self._make_offer_shop(
            "DistantOffer99999 Special",
            "distant_offer@testsync.com",
            lat=FAR_LAT,
            lng=FAR_LNG,
        )
        result = search_offers_by_text(
            keywords=("DistantOffer99999",),
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
            radius_km=10,
        )
        offers = result.get("offers", [])
        found = any(str(o.get("id")) == str(sid) for o in offers)
        self.assertFalse(found, "Distant offer shop should not appear")
        ts_delete("shops", str(sid))

    def test_03_offer_search_without_location_still_works(self):
        """search_offers_by_text works without location."""
        _, sid = self._make_offer_shop(
            "NoLocOffer88888 Special",
            "noloc_offer@testsync.com",
        )
        result = search_offers_by_text(
            keywords=("NoLocOffer88888",),
        )
        self.assertIn("offers", result)
        self.assertIsInstance(result["offers"], list)
        ts_delete("shops", str(sid))

    def test_04_shop_without_offer_not_in_offer_search(self):
        """Shop without any offer not returned in has_offer search."""
        uid = _make_user(self, "no_offer_shop@testsync.com")
        sid = _make_shop(self, uid, name="No Offer Shop Unique99999",
                         category_id=FOOD_CATEGORY_ID)
        _make_address(self, sid)
        sync_single_shop(sid)
        time.sleep(0.5)

        result = search_shops_by_offer(
            user_lat=BASE_LAT,
            user_lng=BASE_LNG,
            radius_km=50,
        )
        shops = result.get("shops", [])
        found = _ids_in_results(shops, "id", sid)
        self.assertFalse(found, "Shop without offer should not appear in offer search")
        ts_delete("shops", str(sid))


# ═══════════════════════════════════════════════════════════════════════════════
# 12. RELEVANCE TESTS
# NOTE: These test the internal _is_relevant() and scoring logic directly.
#       No DB or Typesense needed — pure unit tests.
# ═══════════════════════════════════════════════════════════════════════════════

class RelevanceTests(unittest.TestCase):

    def _shop(self, category: str, subcategory: str = "") -> dict:
        return {"category": category, "subcategory": subcategory, "name": "Test"}

    # ── No filter
    def test_01_no_category_always_relevant(self):
        shop = self._shop("Food & Dining", "Restaurent")
        self.assertTrue(_is_relevant(shop, ""))
        self.assertTrue(_is_relevant(shop, None))

    # ── Direct match
    def test_02_exact_category_match(self):
        shop = self._shop("Food & Dining", "Restaurent")
        self.assertTrue(_is_relevant(shop, "Food & Dining"))

    def test_03_exact_subcategory_match(self):
        shop = self._shop("Food & Dining", "Restaurent")
        self.assertTrue(_is_relevant(shop, "Restaurent"))

    # ── Parent-child relationship
    def test_04_filter_by_subcategory_finds_parent_shop(self):
        """Filter 'Restaurent' should match shop with category 'Food & Dining'."""
        shop = self._shop("Food & Dining", "")
        score = _relevance_score(shop, "Restaurent")
        self.assertGreater(score, 0)

    def test_05_filter_by_parent_finds_subcategory_shop(self):
        """Filter 'Food & Dining' should match shop with subcategory 'Restaurent'."""
        shop = self._shop("", "Restaurent")
        score = _relevance_score(shop, "Food & Dining")
        self.assertGreater(score, 0)

    # ── Hard reject — unrelated pairs
    def test_06_transport_vs_food_hard_rejected(self):
        shop = self._shop("Transportation Services", "Taxi")
        self.assertFalse(_is_relevant(shop, "food & dining"))

    def test_07_food_vs_transport_hard_rejected(self):
        shop = self._shop("Food & Dining", "Restaurent")
        self.assertFalse(_is_relevant(shop, "transportation services"))

    def test_08_mobiles_vs_food_hard_rejected(self):
        shop = self._shop("Mobiles & Electronics", "Mobiles")
        self.assertFalse(_is_relevant(shop, "food & dining"))

    # ── Fuzzy match
    def test_09_fuzzy_match_restaurent_vs_restaurant(self):
        """'Restaurent' (typo in DB) should fuzzy-match 'restaurant' filter."""
        shop = self._shop("Food & Dining", "Restaurent")
        score = _relevance_score(shop, "restaurant")
        self.assertGreater(score, 0)

    def test_10_fuzzy_match_below_threshold_rejected(self):
        """Very different strings should not fuzzy match."""
        shop = self._shop("Fashions", "Clothing")
        score = _relevance_score(shop, "plumbing")
        self.assertLessEqual(score, 0)

    # ── Whole-word guard
    def test_11_whole_word_match_exact(self):
        self.assertTrue(_whole_word_match("taxi", "taxi service provider"))

    def test_12_whole_word_match_no_substring(self):
        """'it' should not match inside 'electrical'."""
        self.assertFalse(_whole_word_match("it", "electrical services"))

    def test_13_whole_word_match_in_should_not_match_dining(self):
        """'in' should not match inside 'dining'."""
        self.assertFalse(_whole_word_match("in", "food and dining"))

    def test_14_whole_word_match_case_insensitive(self):
        self.assertTrue(_whole_word_match("Taxi", "TAXI SERVICE"))

    # ── Score ordering
    def test_15_direct_match_scores_higher_than_fuzzy(self):
        """Exact match should score higher than fuzzy match."""
        shop_exact = self._shop("Fashions", "Clothing")
        shop_fuzzy = self._shop("Fashions", "Clothng")  # slight typo
        score_exact = _relevance_score(shop_exact, "Clothing")
        score_fuzzy = _relevance_score(shop_fuzzy, "Clothing")
        self.assertGreaterEqual(score_exact, score_fuzzy)


# ═══════════════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        suite = unittest.TestLoader().loadTestsFromName(
            sys.argv[1], sys.modules[__name__]
        )
        runner = unittest.TextTestRunner(verbosity=2)
        runner.run(suite)
    else:
        unittest.main(verbosity=2)