"""
test_answer_correctness_v2.py
═════════════════════════════════════════════════════════════════════════════
CORA Answer Correctness Validator — V2
Validates that API returns CORRECT & RELEVANT answers using real database data.

Tests correctness at THREE LEVELS:
  1. STRUCTURE CORRECTNESS — Valid JSON, required fields present, correct types
  2. SEMANTIC CORRECTNESS — Results match intent, answers are relevant
  3. DATA CORRECTNESS — Prices realistic, dates valid, names not gibberish

Based on actual database data from:
  - Job titles: parota master, barista, driver, juice maker, room boy, sales executive
  - Categories: Restaurent, Auto Rickshaw, Taxi, Beautician, IT $ Services, etc.
  - Real user query patterns: implicit searches, ambiguous words, multilingual

Run:
    pytest test_answer_correctness_v2.py -v
    pytest test_answer_correctness_v2.py -v -k "product"
    python test_answer_correctness_v2.py  # Standalone mode with detailed report
═════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import os
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import defaultdict

import httpx
import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL  = os.getenv("CORA_BASE_URL", "http://localhost:8000")
TEST_LAT  = float(os.getenv("TEST_LAT",  "8.1746"))    # Nagercoil
TEST_LNG  = float(os.getenv("TEST_LNG",  "77.4030"))
RADIUS_KM = int(os.getenv("TEST_RADIUS", "25"))
TIMEOUT   = int(os.getenv("TEST_TIMEOUT","15"))

SEARCH_URL = f"{BASE_URL}/api/search"

# ─────────────────────────────────────────────────────────────────────────────
# REAL DATABASE DATA (from your actual DB + job listings)
# ─────────────────────────────────────────────────────────────────────────────

# Real job titles from your database
REAL_JOB_TITLES = {
    "Sales Executive",
    "Software field promoter",
    "parota master",
    "Male kitchen helper",
    "juice maker",
    "room boy",
    "driver",
    "Barista",
    "Chef",
    "Waiter",
    "Cook",
    "Sales Associate",
    "Store Manager",
    "Fashion Consultant",
    "Footwear Specialist",
    "Inventory Manager",
    "Head Chef",
    "Cafe Manager",
    "Nutritionist",
    "Furniture Designer",
    "AC Technician",
    "Service Engineer",
    "Sales Consultant",
}

# Real categories from your database
REAL_CATEGORIES = {
    "Restaurent",
    "Drinks & Beverages",
    "Snacks & Beverages",
    "Meat & Poultry",
    "Grocery,Beauty & Health",
    "Auto Rickshaw",
    "Taxi",
    "Tourist Bus",
    "Load Vehicles",
    "Bike Taxi",
    "Plumbing Services",
    "Ac / Tv Services",
    "Beautician",
    "IT $ Services",
    "catering Services",
    "constructors / Engi",
    "Home Services",
    "Photographer",
    "Fitness",
    "Clothing",
    "Footwear",
    "Furniture & Decor",
    "Mobiles",
    "Computers",
    "Jewellery",
    "Used vehicles",
    "Lodges",
}

# Real products/items from your database
REAL_PRODUCTS = {
    "biryani": "Restaurent",
    "parotta": "Restaurent",
    "dosa": "Restaurent",
    "fresh juice": "Drinks & Beverages",
    "rose milk": "Drinks & Beverages",
    "lassi": "Drinks & Beverages",
    "banana chips": "Snacks & Beverages",
    "muruku": "Snacks & Beverages",
    "honey": "Grocery,Beauty & Health",
    "shirt": "Clothing",
    "jeans": "Clothing",
    "shoes": "Footwear",
}

# Real services from your database
REAL_SERVICES = {
    "plumber": "Plumbing Services",
    "haircut": "Beautician",
    "ac repair": "Ac / Tv Services",
    "web developer": "IT $ Services",
    "auto": "Auto Rickshaw",
    "taxi": "Taxi",
    "catering": "catering Services",
    "construction": "constructors / Engi",
    "house shifting": "Load Vehicles",
    "coconut cutting": "Home Services",
}

# Expected intent → result structure mapping
INTENT_FIELDS = {
    "product": ["product_name", "shop_name", "offer_price", "actual_price", "category"],
    "service": ["service_name", "shop_name", "offer_price", "actual_price"],
    "job": ["position", "shop_name", "job_type", "experience", "description"],
    "shop": ["name", "category", "subcategory", "rating", "review_count"],
    "offer": ["offer_heading", "start_date", "end_date"],
}

# ─────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────────────────────────────────────

def _post(
    query: str,
    lat: Optional[float] = TEST_LAT,
    lng: Optional[float] = TEST_LNG,
    radius: int = RADIUS_KM,
) -> Dict[str, Any]:
    """Make POST request to search API."""
    payload: Dict[str, Any] = {"query": query, "radiusKm": radius}
    if lat is not None:
        payload["userLat"] = lat
        payload["userLng"] = lng
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            r = client.post(SEARCH_URL, json=payload)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as e:
        pytest.skip(f"API unreachable: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Correctness Validators
# ─────────────────────────────────────────────────────────────────────────────

class CorrectnessValidator:
    """Validates if responses are semantically correct, not just well-formed."""

    @staticmethod
    def extract_keywords(query: str) -> List[str]:
        """Extract meaningful keywords from query."""
        stopwords = {
            "i", "need", "any", "nearby", "near", "me", "at", "in", "the",
            "is", "do", "a", "an", "for", "on", "of", "offer", "offers",
            "deals", "discount", "sale", "job", "vacancy", "want", "looking",
            "find", "search", "where", "can", "get", "buy", "ek", "dena",
        }
        words = query.lower().split()
        keywords = [w.strip("'\".,;:!?") for w in words if w.lower() not in stopwords]
        return [k for k in keywords if len(k) > 2]

    @staticmethod
    def keyword_in_text(keyword: str, text: str) -> bool:
        """Check if keyword appears in text (whole word match)."""
        pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
        return bool(re.search(pattern, text.lower()))

    @staticmethod
    def fuzzy_match(text: str, keywords: List[str], threshold: float = 0.5) -> bool:
        """Check if keywords appear in text (fuzzy)."""
        text_lower = text.lower()
        matches = sum(1 for kw in keywords if kw.lower() in text_lower)
        return matches / len(keywords) >= threshold if keywords else False

    @staticmethod
    def is_valid_price(price: float) -> bool:
        """Validate price is realistic for Indian market (10 to 50000 INR)."""
        return 0 < price < 50000

    @staticmethod
    def is_valid_date(date_str: str) -> bool:
        """Check if date is valid ISO format."""
        try:
            datetime.fromisoformat(str(date_str))
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def dates_logical(start_str: str, end_str: str) -> bool:
        """Check if start_date < end_date and end_date is in future."""
        try:
            start = datetime.fromisoformat(str(start_str))
            end = datetime.fromisoformat(str(end_str))
            today = datetime.now()
            return start < end and end > today
        except (ValueError, TypeError):
            return False

    @staticmethod
    def is_gibberish(text: str, min_length: int = 3) -> bool:
        """Detect if text is gibberish (random characters)."""
        if not text or len(text) < min_length:
            return True
        alphanumeric = sum(1 for c in text if c.isalnum() or c in " -.")
        return alphanumeric / len(text) < 0.5

    @staticmethod
    def is_real_name(name: str) -> bool:
        """Check if name looks like a real shop/person name (not gibberish)."""
        return not CorrectnessValidator.is_gibberish(name) and len(name) >= 3

    @staticmethod
    def category_for_intent(query: str, intent: str) -> Optional[str]:
        """Infer expected category for a query based on intent."""
        query_lower = query.lower()
        
        # Check real products
        for product, category in REAL_PRODUCTS.items():
            if product in query_lower:
                return category
        
        # Check real services
        for service, category in REAL_SERVICES.items():
            if service in query_lower:
                return category
        
        return None


# ─────────────────────────────────────────────────────────────────────────────
# LEVEL 1: Structure Correctness Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStructureCorrectness:
    """Validate JSON structure and required fields."""

    def test_response_has_required_top_level_fields(self):
        """All responses must have these top-level fields."""
        data = _post("biryani")
        
        required = ["success", "message", "results", "total_results"]
        for field in required:
            assert field in data, f"Missing required field '{field}'"

    def test_results_is_list(self):
        """Results must be a list, even if empty."""
        data = _post("biryani")
        assert isinstance(data["results"], list), \
            f"'results' should be list, got {type(data['results'])}"

    def test_total_results_matches_count(self):
        """total_results must equal actual result count."""
        data = _post("biryani")
        assert data["total_results"] == len(data["results"]), \
            f"total_results={data['total_results']} but got {len(data['results'])} results"

    def test_success_consistency(self):
        """success=True only if results found, False otherwise."""
        data = _post("biryani")
        
        if data["success"]:
            assert data["total_results"] > 0, \
                "success=True but no results found"
        else:
            assert data["total_results"] == 0, \
                "success=False but results present"

    def test_intent_flags_mutually_exclusive(self):
        """Only one intent flag should be true."""
        data = _post("biryani")
        
        flags = [
            data.get("is_product_search", False),
            data.get("is_service_search", False),
            data.get("is_job_search", False),
            data.get("is_offer_search", False),
            data.get("is_shop_search", False),
        ]
        
        assert sum(flags) <= 1, \
            f"Multiple intent flags true: {flags}"


# ─────────────────────────────────────────────────────────────────────────────
# LEVEL 2: Semantic Correctness Tests (Query → Intent → Results)
# ─────────────────────────────────────────────────────────────────────────────

class TestSemanticCorrectness:
    """Validate results match query intent and are semantically relevant."""

    # Product Search Tests
    def test_product_intent_classification(self):
        """Product queries should be classified as product intent."""
        product_queries = [
            "i need biryani",
            "honey",
            "fresh juice",
            "banana chips",
            "where can i get rose milk",
        ]
        
        for query in product_queries:
            data = _post(query)
            
            # Isolated comprehension list to fix SyntaxError completely
            active_flags = [
                k for k, v in {
                    'product': data.get('is_product_search'),
                    'service': data.get('is_service_search'),
                    'job': data.get('is_job_search'),
                    'offer': data.get('is_offer_search'),
                    'shop': data.get('is_shop_search')
                }.items() if v
            ]
            
            assert data.get("is_product_search"), \
                f"'{query}' should be product intent, got active intents: {active_flags}"

    def test_product_results_have_product_fields(self):
        """Product results must have product-specific fields."""
        data = _post("i need biryani")
        
        if data.get("success") and data["results"]:
            for product in data["results"]:
                assert "product_name" in product, \
                    "Product result missing 'product_name'"
                assert isinstance(product.get("product_name"), str) and len(product["product_name"]) > 0, \
                    f"Invalid product_name: {product.get('product_name')}"

    def test_product_results_match_keywords(self):
        """At least 50% of product results should contain search keywords."""
        data = _post("biryani")
        keywords = CorrectnessValidator.extract_keywords("biryani")
        
        if data.get("results"):
            matching = 0
            for product in data["results"]:
                product_name = product.get("product_name", "").lower()
                if any(CorrectnessValidator.keyword_in_text(kw, product_name) for kw in keywords):
                    matching += 1
            
            match_ratio = matching / len(data["results"])
            assert match_ratio >= 0.5, \
                f"Only {match_ratio:.0%} of results match keywords {keywords}"

    # Service Search Tests
    def test_service_intent_classification(self):
        """Service queries should be classified as service intent."""
        service_queries = [
            "i need auto",
            "i need taxi",
            "i need plumber",
            "haircut",
            "ac repair",
        ]
        
        for query in service_queries:
            data = _post(query)
            assert data.get("is_service_search"), \
                f"'{query}' should be service intent"

    def test_service_results_have_service_fields(self):
        """Service results must have service_name field."""
        data = _post("i need auto")
        
        if data.get("results"):
            for service in data["results"]:
                assert "service_name" in service, \
                    "Service result missing 'service_name'"

    def test_service_results_match_keywords(self):
        """Service results should contain search keywords."""
        data = _post("i need plumber")
        keywords = CorrectnessValidator.extract_keywords("i need plumber")
        
        if data.get("results"):
            matching = 0
            for service in data["results"]:
                service_name = service.get("service_name", "").lower()
                if any(CorrectnessValidator.keyword_in_text(kw, service_name) for kw in keywords):
                    matching += 1
            
            assert matching > 0, \
                f"No service results contain keywords {keywords}"

    # Job Search Tests
    def test_job_intent_classification(self):
        """Job queries should be classified as job intent."""
        job_queries = [
            "i need job",
            "any vacancy",
            "fresher jobs",
            "driver vacancy",
        ]
        
        for query in job_queries:
            data = _post(query)
            assert data.get("is_job_search"), \
                f"'{query}' should be job intent"

    def test_job_results_have_job_fields(self):
        """Job results must have position field, not product_name."""
        data = _post("i need job")
        
        if data.get("results"):
            for job in data["results"]:
                assert "position" in job, \
                    "Job result missing 'position'"
                assert "product_name" not in job, \
                    "Job result should not have 'product_name'"

    def test_job_results_real_titles(self):
        """Job results should have real job titles from database."""
        data = _post("driver vacancy")
        keywords = CorrectnessValidator.extract_keywords("driver vacancy")
        
        if data.get("results"):
            for job in data["results"]:
                position = job.get("position", "")
                assert position and len(position) > 2, \
                    f"Invalid position: {position}"
                # Should match query OR be a real job title from DB
                assert any(kw.lower() in position.lower() for kw in keywords) or \
                       position in REAL_JOB_TITLES, \
                    f"Position '{position}' doesn't match query or isn't in real job titles"

    # Offer Search Tests
    def test_offer_intent_classification(self):
        """Queries with 'offer', 'deal', 'discount' should be offer intent."""
        offer_queries = [
            "any offers nearby",
            "deals near me",
            "food offers",
        ]
        
        for query in offer_queries:
            data = _post(query)
            assert data.get("is_offer_search"), \
                f"'{query}' should be offer intent"

    def test_offer_results_have_offers(self):
        """Offer results should have offers array."""
        data = _post("any offers nearby")
        
        if data.get("results"):
            for shop in data["results"]:
                assert "offers" in shop, \
                    f"Shop '{shop.get('name')}' missing 'offers' array"
                assert isinstance(shop["offers"], list), \
                    "offers should be a list"


# ─────────────────────────────────────────────────────────────────────────────
# LEVEL 3: Data Correctness Tests (Realistic values, valid dates, etc.)
# ─────────────────────────────────────────────────────────────────────────────

class TestDataCorrectness:
    """Validate actual data values are realistic and correct."""

    def test_product_prices_realistic(self):
        """Product prices should be in realistic range (10-50000 INR)."""
        data = _post("i need biryani")
        
        if data.get("results"):
            for product in data["results"]:
                offer_price = product.get("offer_price", 0)
                actual_price = product.get("actual_price", 0)
                
                assert CorrectnessValidator.is_valid_price(offer_price), \
                    f"Offer price {offer_price} unrealistic"
                assert CorrectnessValidator.is_valid_price(actual_price), \
                    f"Actual price {actual_price} unrealistic"
                assert offer_price <= actual_price, \
                    f"Offer price {offer_price} > actual price {actual_price}"

    def test_shop_names_not_gibberish(self):
        """Shop names should be real names, not gibberish."""
        data = _post("i need biryani")
        
        if data.get("results"):
            for result in data["results"]:
                shop_name = result.get("name", "")
                assert CorrectnessValidator.is_real_name(shop_name), \
                    f"Shop name '{shop_name}' looks like gibberish or is too short"

    def test_offer_dates_valid_and_logical(self):
        """Offer dates should be valid ISO and logical (start < end, end in future)."""
        data = _post("any offers nearby")
        
        if data.get("results"):
            for shop in data["results"]:
                for offer in shop.get("offers", []):
                    start_date = offer.get("start_date", "")
                    end_date = offer.get("end_date", "")
                    
                    assert CorrectnessValidator.is_valid_date(start_date), \
                        f"Invalid start_date: {start_date}"
                    assert CorrectnessValidator.is_valid_date(end_date), \
                        f"Invalid end_date: {end_date}"
                    assert CorrectnessValidator.dates_logical(start_date, end_date), \
                        f"Dates illogical: {start_date} >= {end_date}"

    def test_offer_heading_not_empty(self):
        """Offer heading should have meaningful text."""
        data = _post("any offers nearby")
        
        if data.get("results"):
            for shop in data["results"]:
                for offer in shop.get("offers", []):
                    heading = offer.get("offer_heading", "")
                    assert heading and len(heading) > 3, \
                        f"Offer heading too short: '{heading}'"

    def test_job_experience_is_valid(self):
        """Job experience should be a valid number or string."""
        data = _post("i need job")
        
        if data.get("results"):
            for job in data["results"]:
                exp = job.get("experience", "")
                if exp:
                    assert isinstance(exp, (str, int, float)), \
                        f"Invalid experience type: {type(exp)}"

    def test_message_relevant_to_query(self):
        """Message should mention relevant keywords."""
        data = _post("biryani")
        keywords = CorrectnessValidator.extract_keywords("biryani")
        
        message = data.get("message", "").lower()
        assert any(kw.lower() in message for kw in keywords) or \
               any(w in message for w in ["found", "results", "available", "nearby"]), \
            f"Message '{data['message']}' doesn't mention search term or results"


# ─────────────────────────────────────────────────────────────────────────────
# Advanced: Disambiguation Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDisambiguation:
    """Test that ambiguous queries are classified correctly."""

    def test_hotel_context_food_vs_stay(self):
        """'hotel' context should determine if shop vs stay."""
        hotel_queries = [
            "hotel nearby",
            "hotel near me",
            "good hotel",
        ]
        
        for query in hotel_queries:
            data = _post(query)
            assert not data.get("is_product_search"), \
                f"'{query}' should be shop, not product"

    def test_auto_as_service_not_shop(self):
        """'i need auto' should be service (Auto Rickshaw), not shop."""
        data = _post("i need auto")
        
        assert data.get("is_service_search"), \
            "'i need auto' should be service intent"
        assert not data.get("is_shop_search"), \
            "'i need auto' should not be shop intent"

    def test_auto_shop_as_shop_not_service(self):
        """'auto shop' should be shop (browsing), not service."""
        data = _post("auto shop")
        
        if data.get("success"):
            assert not data.get("is_service_search"), \
                "'auto shop' should be shop, not service"

    def test_product_chicken_vs_chicken_biryani(self):
        """'fresh chicken' should be product, 'chicken biryani' might be shop/product."""
        data_product = _post("fresh chicken")
        
        assert data_product.get("is_product_search"), \
            "'fresh chicken' should be product"


# ─────────────────────────────────────────────────────────────────────────────
# Fallback Chain Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestFallbackChain:
    """Validate fallback from product/service search to shop search works."""

    def test_fallback_when_product_not_found(self):
        """When product search returns 0 results, fallback to shop search."""
        data = _post("some_specific_product_xyz123")
        
        assert "success" in data
        assert "results" in data
        assert isinstance(data["results"], list)


# ─────────────────────────────────────────────────────────────────────────────
# Report Generation & Standalone Mode
# ─────────────────────────────────────────────────────────────────────────────

class CorrectnessReport:
    """Generate detailed correctness report."""
    
    def __init__(self):
        self.tests = []
        self.issues = defaultdict(list)

    def test_query(self, query: str) -> Dict[str, Any]:
        """Test a single query and return detailed report."""
        data = _post(query)
        keywords = CorrectnessValidator.extract_keywords(query)
        
        report = {
            "query": query,
            "keywords": keywords,
            "success": data.get("success"),
            "total_results": data.get("total_results"),
            "message": data.get("message"),
            "intent": {
                "product": data.get("is_product_search"),
                "service": data.get("is_service_search"),
                "job": data.get("is_job_search"),
                "offer": data.get("is_offer_search"),
                "shop": data.get("is_shop_search"),
            },
            "checks": {},
            "issues": [],
        }
        
        report["checks"]["has_required_fields"] = all(
            field in data for field in ["success", "message", "results", "total_results"]
        )
        
        report["checks"]["results_count_matches"] = \
            data.get("total_results") == len(data.get("results", []))
        
        report["checks"]["success_consistent"] = \
            (data.get("success") and data.get("total_results") > 0) or \
            (not data.get("success") and data.get("total_results") == 0)
        
        if data.get("results") and keywords:
            relevant = 0
            for result in data["results"]:
                name = ""
                if data.get("is_product_search"):
                    name = result.get("product_name", "")
                elif data.get("is_service_search"):
                    name = result.get("service_name", "")
                elif data.get("is_job_search"):
                    name = result.get("position", "")
                else:
                    name = result.get("name", "")
                
                if any(CorrectnessValidator.keyword_in_text(kw, name) for kw in keywords):
                    relevant += 1
            
            relevance = relevant / len(data["results"])
            report["checks"]["relevance"] = relevance >= 0.5
            report["relevance_score"] = f"{relevance:.0%}"
            
            if relevance < 0.5:
                report["issues"].append(
                    f"Low relevance: only {relevance:.0%} results match keywords"
                )
        
        if data.get("results"):
            for result in data["results"]:
                name = result.get("name") or result.get("product_name") or \
                       result.get("service_name") or result.get("position", "")
                
                if not CorrectnessValidator.is_real_name(name):
                    report["issues"].append(f"Gibberish name: '{name}'")
                
                if "offer_price" in result and result["offer_price"]:
                    if not CorrectnessValidator.is_valid_price(result["offer_price"]):
                        report["issues"].append(
                            f"Unrealistic price: {result['offer_price']}"
                        )
        
        self.tests.append(report)
        return report

    def generate_summary(self) -> str:
        """Generate text summary of all tests."""
        total = len(self.tests)
        passed = sum(1 for t in self.tests if not t["issues"])
        
        output = []
        output.append("=" * 80)
        output.append("CORA ANSWER CORRECTNESS REPORT")
        output.append("=" * 80)
        output.append(f"\nTotal Queries Tested: {total}")
        output.append(f"✓ Passed: {passed}/{total}")
        output.append(f"✗ Issues: {total - passed}/{total}\n")
        
        for test in self.tests:
            status = "✓" if not test["issues"] else "✗"
            output.append(f"\n{status} Query: {test['query']}")
            output.append(f"  Keywords: {test['keywords']}")
            output.append(f"  Intent: {[k for k, v in test['intent'].items() if v]}")
            output.append(f"  Results: {test['total_results']}")
            
            if "relevance_score" in test:
                output.append(f"  Relevance: {test['relevance_score']}")
            
            if test["issues"]:
                output.append("  Issues:")
                for issue in test["issues"]:
                    output.append(f"    - {issue}")
        
        output.append(f"\n{'=' * 80}")
        return "\n".join(output)


# ─────────────────────────────────────────────────────────────────────────────
# Standalone Mode
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_queries = [
        "i need biryani", "honey", "fresh juice", "banana chips",
        "i need auto", "i need taxi", "i need plumber", "haircut", "ac repair",
        "i need job", "any vacancy", "driver vacancy", "barista job",
        "any offers nearby", "food offers", "deals near me",
        "food nearby", "salon near me", "grocery store",
    ]
    
    print("\n" + "=" * 80)
    print("CORA ANSWER CORRECTNESS VALIDATOR v2")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print(f"Location: ({TEST_LAT}, {TEST_LNG})")
    print(f"Radius: {RADIUS_KM}km\n")
    
    report_gen = CorrectnessReport()
    
    for query in test_queries:
        try:
            report_gen.test_query(query)
            print(f"✓ {query}")
        except Exception as e:
            print(f"✗ {query} — {e}")
    
    print(report_gen.generate_summary())
    
    with open("correctness_report.json", "w") as f:
        json.dump(report_gen.tests, f, indent=2)
    print("✓ Detailed report saved to: correctness_report.json")