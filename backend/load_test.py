import asyncio
import argparse
import time
import random
import statistics
from typing import List, Dict
import httpx

QUERY_MIX = [
    {"query": "biryani near me",     "weight": 15},
    {"query": "salon nearby",        "weight": 10},
    {"query": "plumber",             "weight": 8},
    {"query": "jobs near me",        "weight": 8},
    {"query": "offers nearby",       "weight": 7},
    {"query": "pizza shop",          "weight": 5},
    {"query": "doctor clinic",       "weight": 5},
    {"query": "grocery store",       "weight": 5},
    {"query": "ac repair",           "weight": 4},
    {"query": "electrician nearby",  "weight": 4},
    {"query": "Royal Bakery",        "weight": 3},
    {"query": "fresh juice shop",    "weight": 3},
    {"query": "tailor shop near me", "weight": 3},
    {"query": "mobile repair",       "weight": 3},
    {"query": "driving vacancy",     "weight": 2},
    {"query": "hi",                  "weight": 5},
    {"query": "hello",               "weight": 5},
    {"query": "thanks",              "weight": 5},
]

_QUERIES: List[str] = []
for item in QUERY_MIX:
    _QUERIES.extend([item["query"]] * item["weight"])


def _pick_query(index: int) -> str:
    return _QUERIES[index % len(_QUERIES)]


async def _single_request(
    client: httpx.AsyncClient,
    base_url: str,
    query: str,
    results: List[Dict],
) -> None:
    payload = {
        "query":    query,
        "userLat":  13.0827,
        "userLng":  80.2707,
        "radiusKm": 10,
    }
    start = time.monotonic()
    try:
        resp = await client.post(
            f"{base_url}/api/v1/search",
            json=payload,
            timeout=15.0,
        )
        elapsed = time.monotonic() - start
        results.append({
            "status":  resp.status_code,
            "latency": elapsed,
            "ok":      resp.status_code == 200,
            "query":   query,
        })
        # Progress indicator
        ok_count = sum(1 for r in results if r["ok"])
        print(f"\r  Requests: {len(results)} | Success: {ok_count} | Failed: {len(results)-ok_count}", end="", flush=True)
    except httpx.TimeoutException:
        elapsed = time.monotonic() - start
        results.append({"status": 0, "latency": elapsed, "ok": False, "query": query})
        ok_count = sum(1 for r in results if r["ok"])
        print(f"\r  Requests: {len(results)} | Success: {ok_count} | Failed: {len(results)-ok_count}", end="", flush=True)
    except Exception:
        elapsed = time.monotonic() - start
        results.append({"status": -1, "latency": elapsed, "ok": False, "query": query})
        ok_count = sum(1 for r in results if r["ok"])
        print(f"\r  Requests: {len(results)} | Success: {ok_count} | Failed: {len(results)-ok_count}", end="", flush=True)


async def _user_session(
    client: httpx.AsyncClient,
    base_url: str,
    user_id: int,
    duration_seconds: int,
    results: List[Dict],
) -> None:
    request_index = user_id
    max_requests = random.randint(5, 8)

    for _ in range(max_requests):
        query = _pick_query(request_index)
        await _single_request(client, base_url, query, results)
        request_index += 1
        await asyncio.sleep(random.uniform(30.0, 90.0))


async def run_session_test(
    base_url: str,
    num_users: int,
    duration_minutes: int = 5,
    ramp_seconds: int = 30,
):
    duration_seconds = duration_minutes * 60
    print(f"\n{'='*60}")
    print(f"Session test: {num_users} users | {duration_minutes} min | ramp {ramp_seconds}s")
    print(f"Each user makes 5-8 requests (one every 30-90s)")
    print(f"{'='*60}")

    results: List[Dict] = []

    async with httpx.AsyncClient(
        limits=httpx.Limits(max_connections=300, max_keepalive_connections=150)
    ) as client:

        async def launch_user(i):
            await asyncio.sleep(i * (ramp_seconds / num_users))
            await _user_session(client, base_url, i, duration_seconds, results)

        await asyncio.gather(*[launch_user(i) for i in range(num_users)])

    print()  # newline after progress indicator
    _print_report(results, num_users, duration_minutes)


def _print_report(results: List[Dict], num_users: int, duration_minutes: int = 0):
    if not results:
        print("No results collected.")
        return

    latencies    = [r["latency"] for r in results]
    ok_count     = sum(1 for r in results if r["ok"])
    err_count    = len(results) - ok_count
    rate_429     = sum(1 for r in results if r["status"] == 429)
    rate_timeout = sum(1 for r in results if r["status"] == 0)

    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]

    total_requests = len(results)
    req_per_user   = total_requests / num_users if num_users else 0
    req_per_minute = total_requests / duration_minutes if duration_minutes else 0

    print(f"\nResults:")
    print(f"  Total requests   : {total_requests}")
    print(f"  Requests/user    : {req_per_user:.1f}")
    print(f"  Requests/minute  : {req_per_minute:.1f}")
    print(f"  Success rate     : {ok_count}/{total_requests} ({100*ok_count/total_requests:.1f}%)")
    print(f"  Errors           : {err_count}  (429={rate_429}, timeout={rate_timeout})")
    print(f"  Latency p50      : {p50*1000:.0f}ms")
    print(f"  Latency p95      : {p95*1000:.0f}ms")
    print(f"  Latency p99      : {p99*1000:.0f}ms")
    print(f"  Min / Max        : {min(latencies)*1000:.0f}ms / {max(latencies)*1000:.0f}ms")

    from collections import Counter
    failed = [r["query"] for r in results if not r["ok"]]
    if failed:
        print(f"\n  Top failing queries:")
        for q, count in Counter(failed).most_common(5):
            print(f"    '{q}' × {count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",      default="http://localhost:8000")
    parser.add_argument("--users",    type=int, default=100)
    parser.add_argument("--duration", type=int, default=5,
                        help="Test duration in minutes")
    parser.add_argument("--ramp",     type=int, default=30,
                        help="Ramp-up seconds")
    args = parser.parse_args()

    asyncio.run(run_session_test(args.url, args.users, args.duration, args.ramp))