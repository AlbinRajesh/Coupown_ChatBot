# Search Flow & Typesense / DB Mapping

This document explains exactly how user searches are processed in this project, what checks run (order), which DB tables are used to build the Typesense index, which `status` columns gate results, and the exact Typesense query parameters used by the search functions. Use this as a reference when inserting/updating documents into Typesense or debugging search behavior.

---

## 1. High-level request flow (order of checks)

When a user issues a search (e.g. "I need biryani" or "find Royal Bakery"), the system follows these steps in order:

1. Request enters FastAPI handler (`/api/v1/search` or legacy `/api/search`).
2. `get_intent_async(query)` is invoked to extract structured intent:
   - Fast-path: `_is_casual_query()` checks greetings/abstract phrases locally and returns `intent: other` without calling the LLM.
   - Otherwise, a Groq LLM call is made (wrapped in `asyncio.to_thread`) to produce a JSON with fields: `intent`, `type`, `keywords`, `specific_type`, `category`, `name`, `radius_km`, `sort_by_rating`.
   - The returned `category` is resolved via `category_mapper.get_semantic_category_two_level()` (local synonyms → fuzzy → Groq fallback).
3. Branch based on `intent` and parsed fields:
   - `intent == other`: return greeting/out-of-scope response.
   - `intent == shop` and offer intent (detected via `_is_offer_intent()`): go to Offer search flow.
   - `intent == shop` and `type == specific` and `_is_valid_name(name)` true: Exact shop lookup via `search_shop_by_name()`.
   - `intent == job` or `job_detail`: Exact job lookup or job search via Typesense job index (`search_job_by_title()` or `search_jobs_typesense`).
   - If user has not shared location (no lat/lng): use rating-based fallback (`search_shops_by_rating()`) which sorts by rating.
   - Otherwise: general geo-based shop search via `search_shops_parallel()`.

Note: Many blocking operations (Groq, Typesense calls, sync DB) are executed inside `asyncio.to_thread(...)` so they run in worker threads.

---

## 2. Typesense queries used (exact params)

The code builds Typesense parameter dicts before calling the client. Below are the canonical parameter sets.

### Shop base params (used by most shop searches)

- Function: `_shop_base_params(keyword, limit)`
- Resulting params:
```json
{
  "q": "<keyword or *>",
  "query_by": "name,subcategory,category,keywords,tags,offer_text,city,landmark",
  "query_by_weights": "4,3,3,2,2,1,1,1",
  "num_typos": 2,
  "per_page": <limit>,
  "prioritize_exact_match": true
}
```
- Additional params commonly added:
  - `filter_by`: e.g. `location:(lat, lng, 25 km)` or `category:=(["Restaurent"]) && location:(lat, lng, 25 km)`
  - `sort_by`: `location(lat, lng):asc` or `rating:desc,location(lat, lng):asc` (when `sort_by_rating=True`).

### Exact shop lookup
- Parameters used by `search_shop_by_name(name, user_lat, user_lng)`:
```json
{
  "q": "<name>",
  "query_by": "name",
  "num_typos": 1,
  "per_page": 1,
  "prioritize_exact_match": true,
  "sort_by": "location(<lat>, <lng>):asc"  // if location provided
}
```

### Job base params
- Function: `_job_base_params(keyword, limit)`
```json
{
  "q": "<keyword or *>",
  "query_by": "position,job_type,shop_name,description,city",
  "query_by_weights": "4,3,2,2,1",
  "num_typos": 2,
  "per_page": <limit>,
  "prioritize_exact_match": true
}
```
- Job searches always include `filter_by: "status:=1"` (active jobs only).
- Sort: when lat/lng present: `location(lat, lng):asc,created_ts:desc`, otherwise `created_ts:desc`.

### Offer search sequence
1. DB: fetch candidate `shop_id` values from `offer` table (only active offers, `o.status = 1` and `o.end_date >= CURDATE()`), optionally filtered by category/subcategory.
2. Typesense: call search with `filter_by: id:[id1, id2, ...] && location:(lat, lng, <radius> km)` and `q: "*"` sorted by distance.
3. DB: fetch actual offer rows for returned shop ids via `get_batch_shop_offers()`.

### Common Typesense call helper behavior
- Calls are wrapped via `resilience.retry_with_backoff` for transient errors.
- Safe wrappers `_safe_search_shops` / `_safe_search_jobs` catch and return `[]` on error.

---

## 3. DB tables used to build Typesense documents

Typesense indices are built from joined SQL queries. The primary tables and important columns are:

### Shops (Typesense `shops` collection)
- Source tables and columns (see `SHOP_JOIN_SQL` in `backend/typesense_setup.py`):
  - `shop_details` (alias `sd`): `id`, `name`, `phone`, `shoplogo`, `status` (important)
  - `shop_address` (alias `sa`): `city`, `latitude`, `longitude`, `arearoadname`, `nearbylandmark` (defaults filtered by `sa.is_default = 1`)
  - `categories` (alias `c`): `categoriesname` → stored as `category`
  - `subcategories` (alias `s`): `subcategoryname` → stored as `subcategory`
  - `reviews` (alias `r`): used to compute `avg_rating` and `review_count`
  - `offer` (alias `o`): used to aggregate `offer_text` and `has_offer`

Key join conditions and behavior (from `SHOP_JOIN_SQL`):
- Only include `sd.status = 1` rows (active shops) when building the main full join query.
- Result object contains `id`, `name`, `phone`, `shoplogo`, `city`, `latitude`, `longitude`, `category`, `subcategory`, `avg_rating`, `review_count`, `offer_text`, etc.
- `build_shop_doc()` transforms DB rows into Typesense documents. `id` is stringified.

### Jobs (Typesense `jobs` collection)
- Source tables and columns (see `JOB_JOIN_SQL`):
  - `jobsdata` (`j`): `id`, `shop_id`, `position`, `job_type`, `experience`, `description`, `created_at`, `status`, `job_endDate`
  - `shop_details` (`sd`): `name` (as `shop_name`), `shoplogo`
  - `shop_address` (`sa`): `city`, `latitude`, `longitude` (default address joined)

Key behavior:
- Job documents include `created_ts` (epoch from `created_at`) used for sorting.
- Jobs import filters `j.status = 1` and ensures `job_endDate` is null or future when listing active jobs.

### Offers table
- Table: `offer` (columns used in code): `shop_id`, `offer_heading`, `offer_price`, `actual_price`, `start_date`, `end_date`, `description`, `status`, `category_id`, `subcategory_id`, `created_at`.
- Offer search selects DISTINCT `shop_id` for active offers (status=1 and end_date >= CURDATE()).

### Queue
- Table: `typesense_sync_queue` — used by MySQL triggers and processed by `process_sync_queue()` in `sync_manage.py`.
  - Fields used: `id`, `shop_id`, `action` (`upsert` | `delete`), `entity_type` (`shop`|`job`), `status` (`pending`|`synced`|`skipped`|`permanently_failed`), `retry_count`, `created_at`, `synced_at`, `error_message`.

---

## 4. `status` columns and gating rules (which rows are considered active)

- `shop_details.status` (sd.status)
  - When building the main Typesense `shops` index, only rows with `sd.status = 1` are included.
  - `sync_single_shop()` also deletes the Typesense doc when `sd.status != 1`.

- `jobsdata.status` (j.status)
  - Job search and Typesense job import only include jobs where `j.status = 1`.
  - Additionally `j.job_endDate IS NULL OR j.job_endDate >= CURDATE()` is enforced to exclude expired jobs.

- `offer.status` (o.status)
  - Offer search and offer aggregation only use offers with `status = 1` and `end_date >= CURDATE()`.

- `typesense_sync_queue.status` controls queue processing and retries:
  - `'pending'` rows are claimed and processed.
  - When an item fails repeatedly it becomes `'permanently_failed'`.

---

## 5. Exact SQL snippets referenced by the code (summaries)

### SHOP_JOIN_SQL (summary)
- Joins `shop_details` → `shop_address` (default) → `categories` → optional `subcategories` → LEFT JOIN `reviews` and `offer` to compute `avg_rating`, `review_count` and `offer_text`.
- Example fields returned (not the full SQL):
```sql
SELECT sd.id, sd.name, sd.phone, sd.shoplogo,
       sa.city, sa.latitude, sa.longitude,
       c.categoriesname AS category,
       s.subcategoryname AS subcategory,
       ROUND(AVG(r.rating), 1) AS avg_rating,
       COUNT(DISTINCT r.id) AS review_count,
       GROUP_CONCAT(DISTINCT o.offer_heading ORDER BY o.created_at DESC SEPARATOR ' | ') as offer_text
FROM shop_details sd
JOIN shop_address sa ON sa.shop_id = sd.id AND sa.is_default = 1
JOIN categories c ON c.id = sd.category_id
LEFT JOIN subcategories s ON s.id = sd.subcategory_id
LEFT JOIN reviews r ON r.shop_id = sd.id
LEFT JOIN offer o ON o.shop_id = sd.id AND o.status = 1 AND o.end_date >= CURDATE()
WHERE sd.status = 1
GROUP BY sd.id, sd.name, ...
```

### JOB_JOIN_SQL (summary)
```sql
SELECT j.id, j.shop_id, j.position, j.job_type, j.experience, j.description, j.created_at, j.status,
       COALESCE(sd.name, '') AS shop_name, COALESCE(sd.shoplogo, '') AS shoplogo,
       sa.city, sa.latitude, sa.longitude
FROM jobsdata j
LEFT JOIN shop_details sd ON sd.id = j.shop_id
LEFT JOIN shop_address sa ON sa.shop_id = j.shop_id AND sa.is_default = 1
WHERE j.status = 1
  AND (j.job_endDate IS NULL OR j.job_endDate >= CURDATE())
```

### OFFER shop id selection (summary used in `search_shops_by_offer`)
- Either by category:
```sql
SELECT DISTINCT o.shop_id
FROM offer o
JOIN categories c ON c.id = o.category_id
WHERE o.status = 1
  AND o.end_date >= CURDATE()
  AND c.categoriesname = %s
LIMIT 100
```
- Or by subcategory:
```sql
SELECT DISTINCT o.shop_id
FROM offer o
JOIN subcategories sc ON sc.id = o.subcategory_id
WHERE o.status = 1
  AND o.end_date >= CURDATE()
  AND sc.subcategoryname = %s
LIMIT 100
```

---

## 6. Examples (concrete end-to-end)

### Example A: "I need biryani" (geo search)
1. `get_intent_async("I need biryani")` returns something like:
```json
{
  "intent":"shop",
  "type":"general",
  "keywords":["biryani","restaurant","food"],
  "category":"Restaurent",
  "name":"",
  "radius_km":0,
  "sort_by_rating":false
}
```
2. `search_shops_parallel(keywords=["biryani","restaurant","food"], category="Restaurent", user_lat=<lat>, user_lng=<lng>, radius_km=25)`
3. For each keyword a Typesense call is made using `_shop_base_params` with `q=<keyword>`, plus `filter_by` built by `_geo_filter`:
```
filter_by = 'subcategory:=(["Restaurent"]) && location:(<lat>, <lng>, 25 km)'
// if category was parent, use category:=[...] instead
```
4. Returned hits are transformed with `_build_shop()` and filtered by `_is_relevant()`.

### Example B: "offers of Royal Bakery" (shop-specific offer lookup)
1. Intent detection marks `specific_type`=offers and `name`="Royal Bakery".
2. `_is_valid_name("Royal Bakery")` → True
3. `search_shop_by_name("Royal Bakery", lat, lng)` uses a Typesense call: `query_by: name`, `per_page: 1`, `num_typos: 1`, prioritized exact match.
4. If a shop is found, `get_batch_shop_offers([shop_id])` reads offers from DB (only `o.status=1` and `o.end_date >= CURDATE()`).

### Example C: "barista job" (job search)
1. `get_intent_async("barista job")` → `intent: job` and keywords.
2. `search_jobs_typesense(keywords, user_lat, user_lng, radius_km)` calls Typesense jobs collection with `filter_by: "status:=1"`.
3. Results are returned and `created_ts` is used to sort (if no location).

---

## 7. Sync flows and maintenance

- Incremental/instant sync:
  - MySQL triggers can insert rows into `typesense_sync_queue`.
  - Webhook endpoints in `sync_routes.py` allow instant `sync_single_shop(shop_id)` or `sync_single_job(job_id)`.
  - `process_sync_queue()` runs every minute (APScheduler) as a safety net; it uses `SELECT ... FOR UPDATE SKIP LOCKED` to claim batches safely across workers.
- Full sync:
  - `sync_all_shops()` and `sync_all_jobs()` perform a full re-import using batched fetches and `_bulk_import()` to Typesense.

---

## 8. Practical notes for inserting/updating Typesense

- Always mirror the `build_shop_doc()` / `build_job_doc()` field names and types.
- Ensure `id` is stringified when calling Typesense.
- Only upsert shops where `shop_details.status = 1`.
- When deleting or marking inactive, call the webhook or push an entry into `typesense_sync_queue` with `action='delete'`.

---

## 9. Health & Monitoring checks to add (recommended)

- Add Typesense health check in `/health` to complement DB check.
- Monitor: DB connection pool usage (provided by `get_pool_stats()`), Redis availability, Typesense latency, and queue backlog (`get_queue_stats()`).

---

## Where to find code
- Intent parsing & routing: `backend/main.py`
- Typesense schema & builders: `backend/typesense_setup.py`
- Search logic: `backend/search.py`
- DB pool and helpers: `backend/database.py`
- Caching: `backend/cache.py`
- Sync queue & background jobs: `backend/sync_manage.py` and `backend/sync_routes.py`


---

If you'd like, I can:
- add a small checklist of monitored metrics and Prometheus queries, or
- produce a short script that exports a single shop document example JSON ready for Typesense `upsert()` based on a DB row.


---
Created on: 2026-05-26
