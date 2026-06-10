"""
category_mapper.py
──────────────────
Semantic category mapping: user query → exact DB subcategory or category name.

DB Structure (exact names):
  Categories (15):
    Fashions, Food & Dining, Home & Living Furnitures, Electrical Appliances,
    Mobiles & Electronics, Books & Stationery, Entertainment, Gifts & Jewels,
    Grocery,Beauty & Health, Sports Products, Services, Automobiles,
    Transportation Services, Travel & Hospitality, Others

  Subcategories (exact DB spelling used throughout):
    Fashions          → Bags & Accessories, Clothing, Footwear, Travel Accessories, Watch & Sunglass
    Food & Dining     → Drinks & Beverages, Restaurent, More
    Home & Living     → Bed & Bath, Furniture & Decor, Kitchen & Dining
    Electrical        → Cooling Appliances, Kitchen Appliances, Refrigerator, Television, Washing Machines
    Mobiles & Elec    → Accessories, Camera, Computers, Headphones & Speakers, Mobiles,
                        Personal Cares, Smart Watches, Tablets
    Books & Stat      → Books, Stationary
    Entertainment     → Events, Movies, Sports, Theme Parks
    Gifts & Jewels    → Flowers, Gifts, Jewellery, Toys
    Grocery,B&H       → Household Care, Personal & Baby Care, Snacks & Beverages, Staples, Vegitables
    Sports Products   → Fitness, Nutrition, Sports
    Services          → Ac / Tv Services, Beautician, catering Services, constructors / Engi,
                        Doctors, Home Services, Installations, IT $ Services, More,
                        Photographer, Plumbing Services, Real estate, Used vehicles
    Automobiles       → Accessories, Bike & Car Selling, Bike & Car Servicing
    Transportation    → Auto Rickshaw, Bike Taxi, Load Vehicles, Taxi, Tourist Bus, Vehicle Rental
    Travel & Hosp     → Bus, Cabs, Flight, Holidays, Lodges, Luxury Resorts, Train
    Others            → Art & Graft, Education, Fitness, Freelance and Gig,
                        Legal and Consulting, Meat & Poultry, Pet Care, Other

Public API:
  get_semantic_category_two_level(user_text, subcategories, categories, groq_client) → str
  get_semantic_category(user_text, available_categories) → str
  get_category_synonyms(subcategory_name) → List[str]
  is_casual(query) → bool
"""

import difflib
import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# CASUAL / NON-SEARCH PHRASES
# ═══════════════════════════════════════════════════════════════════════════════

_CASUAL_PHRASES = {
    "hi", "hello", "hey", "ok", "okay", "yes", "no", "nope", "yep",
    "thanks", "thank you", "thank u", "ty", "bye", "goodbye", "good bye",
    "good morning", "good evening", "good night", "good afternoon",
    "how are you", "how r u", "what's up", "whats up", "sup",
    "sure", "alright", "fine", "great", "nice", "cool", "wow",
    "lol", "haha", "hmm", "ok ok", "got it",
    "what can you do", "what do you do", "who are you", "what is this",
    "what is this app", "help", "help me", "i need help",
    "i am ok", "i am okay", "i am good", "i am fine", "i am bad",
    "i am tired", "i am bored", "i am busy", "i am happy", "i am sad",
    "i need rest", "i need a break", "i need it", "i need time",
    "i need something", "i need anything", "i need everything",
    "i need a minute", "i need money", "i need cash", "i need support",
    "show me", "give me", "tell me", "tell me more",
    "what do you have", "not good", "not bad",
    "just", "nothing", "never mind", "skip",
}


def is_casual(query: str) -> bool:
    """Returns True if query is a greeting or abstract phrase, not a shop search."""
    return query.strip().lower() in _CASUAL_PHRASES


# ═══════════════════════════════════════════════════════════════════════════════
# CANONICAL DB NAMES  (exact spelling from DB — used for return values)
# ═══════════════════════════════════════════════════════════════════════════════

DB_SUBCAT_NAMES = {
    # Fashions
    "bags & accessories":           "Bags & Accessories",
    "clothing":                     "Clothing",
    "footwear":                     "Footwear",
    "travel accessories":           "Travel Accessories",
    "watch & sunglass":             "Watch & Sunglass",
    # Food & Dining
    "drinks & beverages":           "Drinks & Beverages",
    "restaurent":                   "Restaurent",
    # Home & Living Furnitures
    "bed & bath":                   "Bed & Bath",
    "furniture & decor":            "Furniture & Decor",
    "kitchen & dining":             "Kitchen & Dining",
    # Electrical Appliances
    "cooling appliances":           "Cooling Appliances",
    "kitchen appliances":           "Kitchen Appliances",
    "refrigerator":                 "Refrigerator",
    "television":                   "Television",
    "washing machines":             "Washing Machines",
    # Mobiles & Electronics
    "mobiles":                      "Mobiles",
    "tablets":                      "Tablets",
    "computers":                    "Computers",
    "headphones & speakers":        "Headphones & Speakers",
    "camera":                       "Camera",
    "personal cares":               "Personal Cares",
    "smart watches":                "Smart Watches",
    "mobiles & electronics accessories": "Accessories",
    # Books & Stationery
    "books":                        "Books",
    "stationary":                   "Stationary",
    # Entertainment
    "events":                       "Events",
    "movies":                       "Movies",
    "sports entertainment":         "Sports",
    "theme parks":                  "Theme Parks",
    # Gifts & Jewels
    "flowers":                      "Flowers",
    "gifts":                        "Gifts",
    "jewellery":                    "Jewellery",
    "toys":                         "Toys",
    # Grocery,Beauty & Health
    "household care":               "Household Care",
    "personal & baby care":         "Personal & Baby Care",
    "snacks & beverages":           "Snacks & Beverages",
    "staples":                      "Staples",
    "vegitables":                   "Vegitables",
    # Sports Products
    "nutrition":                    "Nutrition",
    "sports products":              "Sports",
    "fitness sports":               "Fitness",
    # Services
    "ac / tv services":             "Ac / Tv Services",
    "beautician":                   "Beautician",
    "catering services":            "catering Services",
    "constructors / engi":          "constructors / Engi",
    "doctors":                      "Doctors",
    "home services":                "Home Services",
    "installations":                "Installations",
    "it $ services":                "IT $ Services",
    "photographer":                 "Photographer",
    "plumbing services":            "Plumbing Services",
    "real estate":                  "Real estate",
    "used vehicles":                "Used vehicles",
    # Automobiles
    "automobiles accessories":      "Accessories",
    "bike & car selling":           "Bike & Car Selling",
    "bike & car servicing":         "Bike & Car Servicing",
    # Transportation Services
    "auto rickshaw":                "Auto Rickshaw",
    "bike taxi":                    "Bike Taxi",
    "load vehicles":                "Load Vehicles",
    "taxi":                         "Taxi",
    "tourist bus":                  "Tourist Bus",
    "vehicle rental":               "Vehicle Rental",
    # Travel & Hospitality
    "bus":                          "Bus",
    "cabs":                         "Cabs",
    "flight":                       "Flight",
    "holidays":                     "Holidays",
    "lodges":                       "Lodges",
    "luxury resorts":               "Luxury Resorts",
    "train":                        "Train",
    # Others
    "art & graft":                  "Art & Graft",
    "education":                    "Education",
    "fitness others":               "Fitness",
    "freelance and gig":            "Freelance and Gig",
    "legal and consulting":         "Legal and Consulting",
    "meat & poultry":               "Meat & Poultry",
    "pet care":                     "Pet Care",
}

DB_CAT_NAMES = {
    "fashions":                     "Fashions",
    "food & dining":                "Food & Dining",
    "home & living furnitures":     "Home & Living Furnitures",
    "electrical appliances":        "Electrical Appliances",
    "mobiles & electronics":        "Mobiles & Electronics",
    "books & stationery":           "Books & Stationery",
    "entertainment":                "Entertainment",
    "gifts & jewels":               "Gifts & Jewels",
    "grocery,beauty & health":      "Grocery,Beauty & Health",
    "sports products":              "Sports Products",
    "services":                     "Services",
    "automobiles":                  "Automobiles",
    "transportation services":      "Transportation Services",
    "travel & hospitality":         "Travel & Hospitality",
    "others":                       "Others",
}


# ═══════════════════════════════════════════════════════════════════════════════
# SUBCATEGORY SYNONYM MAP
# Built from real DB data, actual shop products/services, and real user queries
# ═══════════════════════════════════════════════════════════════════════════════

SYNONYM_MAP: dict[str, list[str]] = {

    # ──────────────────────────────────────────────────────────────────────────
    # FASHIONS
    # ──────────────────────────────────────────────────────────────────────────
    "clothing": [
        # Core terms
        "clothes", "clothing", "apparel", "garment", "outfit", "dress",
        "shirt", "t-shirt", "tshirt", "t shirt", "pant", "trousers",
        "jeans", "denim", "shorts", "skirt", "top", "blouse",
        # Indian specific
        "kurta", "salwar", "saree", "sari", "lehenga", "kurti", "dupatta",
        "lungi", "dhoti", "veshti", "mundu", "churidar", "anarkali",
        "pattu saree", "silk saree", "cotton saree", "ethnic wear",
        "western wear", "indo western", "readymade", "readymade clothes",
        # Store types
        "boutique", "fashion store", "garment store", "cloth shop",
        "clothes shop", "dress shop", "fashion shop", "clothing store",
        "textile", "textiles", "silk", "cotton", "fabric shop",
        # Kids / special
        "kids wear", "childrens wear", "boys wear", "girls wear",
        "school uniform", "uniform shop", "ladies wear", "mens wear",
        "ladies fashion", "mens fashion", "ladies clothing", "mens clothing",
        # Real user queries from data
        "sb fashion", "holy family ladies wear", "nagarajan s clothing",
        "men combo", "ladies combo", "men's combo", "ladies combo",
        "designer wear", "tailor", "stitching", "stitch",
        # Natural language
        "i need clothes", "need clothes", "buy clothes", "where to buy clothes",
        "new dress", "need outfit", "something to wear", "need a dress",
        "need shirt", "need pant", "need jeans", "looking for clothes",
        "clothes near me", "dress near me", "fashion near me",
        "find clothes", "get clothes", "purchase clothes",
        "need new dress", "want new dress", "looking for dress",
        "women clothing", "men clothing", "kid clothing",
    ],

    "footwear": [
        "shoes", "sandals", "chappal", "chappals", "footwear", "sneakers",
        "heels", "boots", "floaters", "slippers", "hawai chappal",
        "sport shoes", "sports shoes", "running shoes", "formal shoes",
        "casual shoes", "kolhapuri", "bata", "vkc", "vkc chappal",
        "popy", "action shoes", "school shoes", "leather shoes",
        "shoe shop", "chappal shop", "sandal shop", "footwear shop",
        "shoe store", "shoe near me",
        "i need shoes", "buy shoes", "need shoes", "new sandals",
        "need sandals", "where to buy shoes", "find shoes",
        "need chappal", "new shoes", "footwear shop near me",
    ],

    "watch & sunglass": [
        "watch", "watches", "wristwatch", "timepiece", "digital watch",
        "analog watch", "wall clock", "clock",
        "sunglass", "sunglasses", "shades", "goggles", "eyewear",
        "spectacles", "glasses", "optical", "optician", "eye glasses",
        "frame", "lens", "contact lens", "power glasses",
        "watch shop", "sunglass shop", "watch store", "optical store",
        "i need watch", "need watch", "buy watch", "new watch",
        "need sunglasses", "buy sunglasses", "where to buy watch",
    ],

    "bags & accessories": [
        "bag", "bags", "handbag", "purse", "wallet", "backpack",
        "luggage", "belt", "suitcase", "trolley bag", "travel bag",
        "school bag", "college bag", "laptop bag", "leather bag",
        "clutch", "tote bag", "side bag", "shoulder bag",
        "accessories", "fashion accessories", "hair accessories",
        "bag shop", "accessories store", "purse shop",
        "i need bag", "need bag", "buy bag", "where to buy bag",
        "need handbag", "new bag",
    ],

    "travel accessories": [
        "travel kit", "travel accessories", "travel gear",
        "travel essentials", "travel products", "travel items",
        "neck pillow", "travel pillow", "luggage tag", "passport cover",
    ],

    # ──────────────────────────────────────────────────────────────────────────
    # FOOD & DINING
    # ──────────────────────────────────────────────────────────────────────────
    "restaurent": [
        # Core
        "restaurant", "restaurants", "food", "eat", "eating", "dine",
        "dining", "hungry", "i am hungry", "need food", "want food",
        "lunch", "dinner", "breakfast", "meal", "meals", "tiffin",
        # Store types
        "dhaba", "mess", "canteen", "eatery", "food place", "eating joint",
        "food stall", "food center", "food court", "hotel", "bhojnalaya",
        "cafe", "cafeteria", "coffee shop", "tea shop", "tea stall",
        # Specific dishes (from real product data)
        "biryani", "biriyani", "briyani", "chicken biryani", "mutton biryani",
        "beef biryani", "veg biryani", "dum biryani", "hyderbad dum briyani",
        "bucket chicken biryani",
        "parotta", "parota", "bun parota", "porotta", "kothu parotta",
        "dosa", "dosai", "plain dosa", "kari dosa", "masala dosa",
        "idly", "idli", "vada", "pongal", "appam", "puttu",
        "chappati", "chapati", "roti", "naan",
        "shawarma", "burger", "pizza", "noodles", "fried rice",
        "chicken", "chicken fry", "grill chicken", "fried chicken",
        "chicken lappa", "beef lappa", "kuzhi paniyaram",
        "thali", "veg food", "non veg food", "south indian", "north indian",
        "chinese food", "chinese foods", "fast food",
        "fish food", "fish meals", "fish meels", "pig meals",
        "uluthan choru", "beef roast", "beef curry", "beef fry",
        "shawarma", "mutton soup", "soup",
        # Juice/cafe items often in restaurants
        "idly", "parotta", "dosai", "meals",
        "lunch meals", "dinner place", "breakfast place",
        # Natural language
        "where to eat", "place to eat", "something to eat",
        "looking for food", "want to eat", "need a restaurant",
        "food near me", "restaurant near me", "give me food",
        "where can i get food", "where is food shop",
        "best restaurant", "need restaurant", "i need biryani",
        "good restaurant", "non veg restaurant", "veg restaurant",
        "south indian food", "north indian food",
        # Real shop names / patterns
        "aha 99", "britto unavagam", "hakkim briyani", "aram briani",
        "sj restaurant", "captain hotel", "hotel", "food corner",
        "food hub", "tiffin center", "tiffen center",
        "adhis food court", "100 rs briyani", "kumari biriyani",
        "puhari tiffen center", "famous hotel",
        "i need food", "find food", "get food",
    ],

    "drinks & beverages": [
        # Core
        "juice", "fresh juice", "fruit juice", "smoothie", "shake",
        "milkshake", "milk shake", "fruit shake",
        "sugarcane juice", "coconut water", "lassi", "cool drink",
        "cold drink", "soft drink", "soda", "lemonade", "beverages",
        # Specific (from real products)
        "rose milk", "badam milk", "sharjah", "falooda", "faloda",
        "mojito", "mojito & crush", "fresh juice and mojito",
        "watermelon juice", "pineapple juice", "pine apple juice",
        "coconut", "tender coconut", "coconut shop",
        "ice cream", "icecream", "scoop ice", "family icecream",
        "puttu icecream", "lazza ice creams",
        "tea", "coffee", "cold coffee",
        "kool", "cool bar", "chill",
        # Store types
        "juice shop", "juice bar", "juice center", "juice stall",
        "cool bar", "juice house", "beverages shop", "fresh juice shop",
        "ice bay", "lassi house", "a1 juice house", "d shakes",
        "cup cozy cafe", "grace fusion cafe", "crispia", "aaryan juice",
        "a1 samosa", "snacks and juice", "juice varieties",
        # Natural language
        "i need juice", "where to buy juice", "juice shop near me",
        "need fresh juice", "cold drink shop", "beverage shop",
        "need juice", "fresh juice near me", "i need cold drink",
        "need lassi", "want coffee", "need tea",
    ],

    # ──────────────────────────────────────────────────────────────────────────
    # HOME & LIVING FURNITURES
    # ──────────────────────────────────────────────────────────────────────────
    "furniture & decor": [
        # Core
        "furniture", "sofa", "sofa set", "sofaset", "chair", "table",
        "wardrobe", "cupboard", "cuboard", "almirah", "shelf",
        "dining set", "study table", "office table", "centre table",
        "bed frame", "cot", "wooden bed", "baby bed", "steel bed",
        "steel bero", "berow", "bero", "cupboard and bed",
        "timbers", "angel timbers", "wood", "wooden furniture",
        # Store types
        "furniture shop", "furniture store", "home decor", "interior",
        "wood furniture", "office furniture", "steel furniture",
        "modular furniture", "furniture & decor", "home furniture",
        "sabarisan furniture", "jayson furniture", "prk furniture",
        "rajan steels", "nagarajan wood works",
        # Real product data
        "wooden bed", "baby bed", "steel bero", "berow",
        "cupboard and bed", "sofaset", "sofa set",
        # Natural language
        "i need furniture", "where to buy furniture", "sofa shop",
        "need sofa", "need chair", "need table", "need cupboard",
        "find furniture", "buy furniture", "furniture near me",
        "need almirah", "need wardrobe", "home interior",
        "wood work", "wood cutting", "carpenter",
        "timbers shop", "timber",
    ],

    "bed & bath": [
        "bed", "mattress", "pillow", "bed sheet", "bedsheet",
        "blanket", "towel", "bathroom accessories", "bath accessories",
        "cot", "baby cot", "bed store", "bath store",
        "i need bed", "where to buy mattress", "bed sheet shop",
        "towel shop", "bathroom shop", "need bed",
    ],

    "kitchen & dining": [
        "kitchen", "utensils", "cookware", "dining table",
        "kitchen accessories", "vessels", "pressure cooker", "pan",
        "kadai", "bowl", "plate", "glass", "kitchen items",
        "kitchen shop", "vessels shop",
        "i need utensils", "where to buy cookware", "kitchen items",
        "need utensils", "need vessels",
    ],

    # ──────────────────────────────────────────────────────────────────────────
    # ELECTRICAL APPLIANCES
    # ──────────────────────────────────────────────────────────────────────────
    "cooling appliances": [
        "ac", "air conditioner", "cooler", "fan", "ceiling fan",
        "table fan", "air cooler", "desert cooler", "pedestal fan",
        "cooling appliance", "ac shop", "air conditioner shop",
        "buy ac", "need ac", "new fan", "buy fan",
        "i need ac", "where to buy fan", "air cooler shop",
        "ceiling fan shop", "fan shop near me",
    ],

    "refrigerator": [
        "fridge", "refrigerator", "freeze", "freezer", "deep freeze",
        "double door fridge", "single door fridge", "mini fridge",
        "buy fridge", "need fridge", "fridge shop",
        "i need fridge", "where to buy refrigerator",
        "refrigerator dealer", "fridge near me",
    ],

    "television": [
        "tv", "television", "led tv", "smart tv", "oled", "lcd",
        "android tv", "new tv", "buy tv",
        "i need tv", "where to buy television", "tv shop",
        "smart tv dealer", "led tv shop", "tv near me",
    ],

    "washing machines": [
        "washing machine", "washer", "laundry machine",
        "front load", "top load", "semi automatic",
        "buy washing machine", "need washing machine",
        "i need washing machine", "where to buy washer",
        "laundry machine shop",
    ],

    "kitchen appliances": [
        "mixer", "grinder", "microwave", "oven", "induction",
        "juicer", "blender", "food processor", "mixer grinder",
        "wet grinder", "toaster", "rice cooker", "electric kettle",
        "kitchen appliance", "buy mixer", "need mixer",
        "i need mixer", "where to buy microwave",
        "blender shop", "oven dealer",
    ],

    # ──────────────────────────────────────────────────────────────────────────
    # MOBILES & ELECTRONICS
    # ──────────────────────────────────────────────────────────────────────────
    "mobiles": [
    # Core
    "mobile", "phone", "smartphone", "cell phone", "mobile phone",
    "new phone", "buy phone", "buy mobile",
    # Brands only (generic)
    "iphone", "samsung", "vivo", "oppo", "realme", "oneplus", 
    "redmi", "xiaomi", "nokia", "android",
    # Services
    "mobile repair", "phone repair", "screen repair",
    "mobile service", "mobile service center", "phone service",
    # Store types (generic only)
    "mobile shop", "phone shop", "mobile store", "phone store",
    "smartphone shop",
    # Accessories
    "mobile accessories", "phone accessories", "charger", "cable",
    "cover", "case", "screen guard", "power bank",
    # Natural language
    "i need mobile", "where to buy phone", "mobile shop near me",
    "need phone", "need mobile", "find mobile shop",
    "electronic", "electronics", "electronic shop",
    ],

    "tablets": [
        "tablet", "ipad", "android tablet", "tab", "samsung tab",
        "buy tablet", "i need tablet", "where to buy tablet",
        "ipad shop", "tab shop",
    ],

    "computers": [
        "computer", "laptop", "pc", "desktop", "notebook",
        "computer shop", "laptop shop", "buy laptop", "buy computer",
        "laptop repair", "computer repair", "laptop service",
        "computer service", "computer sales", "laptop sales",
        "i need laptop", "where to buy laptop",
        "laptop store", "desktop computer", "gaming laptop",
        "need laptop", "find laptop",
    ],

    "headphones & speakers": [
        "headphones", "earphones", "speaker", "earbuds",
        "bluetooth speaker", "headset", "wireless earphones",
        "neckband", "tws", "airpods", "wireless headphones",
        "wired earphones", "bass speaker", "bluetooth headset",
        "i need headphones", "where to buy speaker",
        "earphone shop", "headphone store", "buy earphones",
    ],

    "smart watches": [
        "smart watch", "smartwatch", "fitness band", "wearable",
        "fitness tracker", "activity band", "apple watch",
        "i need smart watch", "buy smartwatch", "smart band",
    ],

    "camera": [
        "camera", "dslr", "digital camera", "action camera", "gopro",
        "mirrorless camera", "camera shop", "photography camera",
        "i need camera", "where to buy dslr",
        "camera store", "buy camera",
    ],

    "personal cares": [
        "hair dryer", "blow dryer", "hair styling", "hair straightener",
        "hair curler", "styler", "trimmer", "shaver", "electric shaver",
        "beard trimmer", "hair iron", "epilator", "grooming kit",
        "grooming appliances", "personal grooming",
    ],

    "mobiles & electronics accessories": [
        "mobile accessories", "phone accessories", "charger", "cable",
        "cover", "case", "screen guard", "power bank", "phone case",
        "mobile cover", "data cable", "usb cable", "otg", "adapter",
        "mobile stand", "smart accorices", "alagy accessories",
    ],

    # ──────────────────────────────────────────────────────────────────────────
    # BOOKS & STATIONERY
    # ──────────────────────────────────────────────────────────────────────────
    "books": [
        "book", "books", "novel", "textbook", "storybook", "comic",
        "magazine", "notebook", "book shop", "bookstore",
        "i need book", "where to buy book", "bookstore near me",
        "buy book", "need book",
    ],

    "stationary": [
        "stationery", "stationary", "pen", "pencil", "eraser",
        "notebook", "school supplies", "office supplies", "paper",
        "file", "folder", "stapler", "scale", "geometry box",
        "stationery shop", "i need stationery",
        "where to buy pen", "office stationery", "school stationery",
        "find stationery", "need pen", "need notebook",
    ],

    # ──────────────────────────────────────────────────────────────────────────
    # ENTERTAINMENT
    # ──────────────────────────────────────────────────────────────────────────
    "movies": [
        "movie", "cinema", "theatre", "film", "multiplex", "show",
        "ticket", "movie ticket", "morning show", "night show",
        "rajesh theatre", "rajesh theatre morning show",
        "4k", "dolby", "audio theatre",
        "i need movie ticket", "where is cinema",
        "movie theatre near me", "cinema booking",
        "movie show", "film ticket", "cinema ticket",
    ],

    "events": [
        "event", "concert", "show", "live event", "exhibition",
        "fair", "function", "event management",
        "wedding event", "party event", "corporate event",
        "i need event", "where to find concert",
        "event tickets", "event organizer", "event planner",
        "event management company",
    ],

    "sports entertainment": [
        "sports equipment", "cricket bat", "football", "badminton racket",
        "sports shop", "sports goods", "gym equipment",
        "sports accessories", "cricket", "football gear",
        "i need sports equipment", "where to buy sports gear",
        "sports store",
    ],

    "theme parks": [
        "theme park", "amusement park", "water park", "fun park",
        "rides", "entertainment park", "i need theme park",
        "where is amusement park", "fun park nearby",
    ],

    # ──────────────────────────────────────────────────────────────────────────
    # GIFTS & JEWELS
    # ──────────────────────────────────────────────────────────────────────────
    "jewellery": [
        "jewellery", "jewelry", "gold", "silver", "bangles", "necklace",
        "earrings", "rings", "ornaments", "imitation jewellery",
        "artificial jewelry", "diamond", "platinum", "gems",
        "gold shop", "jewellery shop", "silver shop",
        "i need jewellery", "where to buy gold",
        "jewellery shop near me", "diamond shop",
        "buy gold", "need jewellery",
    ],

    "gifts": [
        "gift", "gifts", "gift shop", "present", "gift items",
        "birthday gift", "anniversary gift", "return gift",
        "gift store", "gift basket", "gift hamper",
        "i need gift", "where to buy gift",
        "gift shop near me", "need gift",
    ],

    "flowers": [
        "flower", "flowers", "bouquet", "florist", "flower shop",
        "roses", "flower delivery", "fresh flowers",
        "i need flowers", "where to buy flowers",
        "flower shop near me", "need flowers",
    ],

    "toys": [
        "toy", "toys", "toy shop", "kids toys", "games", "board games",
        "children toys", "baby toys", "lego", "action figure",
        "i need toys", "where to buy toys", "toy store",
        "need toys", "buy toys",
    ],

    # ──────────────────────────────────────────────────────────────────────────
    # GROCERY, BEAUTY & HEALTH
    # ──────────────────────────────────────────────────────────────────────────
    "staples": [
        "grocery", "kirana", "supermarket", "daily needs", "provisions",
        "ration", "staples", "pulses", "rice", "flour", "oil", "spices",
        "general store", "grocery shop", "provision store",
        "grocery store", "kirana store", "departmental store",
        "buy groceries", "need groceries", "grocery items",
        "daily essentials", "i need groceries", "where to buy groceries",
        "grosery", "groceries near me", "annachi kadai",
        "dal", "sugar", "salt", "maida", "rava",
        "need rice", "need dal", "vegetables and fruits",
    ],

    "vegitables": [
        "vegetables", "sabzi", "sabji", "fresh vegetables", "greens",
        "veggies", "vegetable market", "vegetable shop", "fruits",
        "fresh fruits", "sabziwala", "vegetable vendor",
        "banana chips", "chips", "dry fruits", "dates and nuts",
        "cashewnuts", "cashew", "jebi vegetables",
        "i need vegetables", "where to buy vegetables",
        "fresh vegetables shop", "fruit shop", "vegitables",
        "need vegetables", "buy vegetables",
    ],

    "snacks & beverages": [
        "snacks", "namkeen", "packaged food", "biscuits", "chips",
        "cold drinks packaged", "packaged beverages", "instant food",
        "muruku", "murukku", "achu muruku", "then kuzhal muruku",
        "munthiri kothu", "athirasam", "adhirasam",
        "snack shop", "farsan", "mixtures", "mixture",
        "crispy snacks", "banana chips", "hot chips",
        "abi nila hot chips", "sree ranga hot chips",
        "annai fish pickles", "dry fish", "karuvaadu",
        # Tamil snacks from real data
        "முந்திரி கொத்து", "அதிரசம்", "then kuzhal mittai",
        "karupatti then mittai", "kuzhi paniyaram thattai",
        "need snacks", "buy snacks",
    ],

    "personal & baby care": [
        "personal care", "baby care", "baby products", "cosmetics",
        "skincare", "haircare products", "toiletries", "diapers",
        "baby food", "baby accessories", "baby shop",
        "i need baby care", "where to buy baby products",
        "cosmetics shop", "skincare shop", "beauty products",
        "face wash", "shampoo", "soap", "cream", "lotion",
    ],

    "household care": [
        "household", "cleaning products", "detergent", "home care",
        "floor cleaner", "dishwash", "phenyl", "cleaning supplies",
        "i need cleaning products", "where to buy detergent",
        "household items shop", "broom", "mop", "cleaning items",
    ],

    # ──────────────────────────────────────────────────────────────────────────
    # SPORTS PRODUCTS
    # ──────────────────────────────────────────────────────────────────────────
    "sports products": [
        "cricket bat", "football", "badminton racket", "shuttle",
        "sports shop", "sports goods", "sports accessories",
        "cricket gear", "football gear", "sports store",
        "buy sports equipment", "sports equipment shop",
        "carmel fitness", "ds fitness",
    ],

    "nutrition": [
        "protein", "whey protein", "supplement", "nutrition",
        "protein powder", "mass gainer", "creatine", "pre workout",
        "health supplement", "i need protein", "where to buy supplements",
        "protein powder shop", "nutrition supplements", "gym supplement",
        "weight gainer", "bcaa",
    ],

    "fitness sports": [
        "fitness", "gym", "workout", "exercise", "weight training",
        "yoga", "zumba", "aerobics", "crossfit", "health club",
        "bodybuilding", "treadmill", "fitness center", "fitness centre",
        "gym center", "gym nearby", "yoga center", "yoga class",
        "pilates", "gym membership", "fitness trainer",
        "yoga studio", "workout center", "carmel fitness centre",
        "ds fitness center",
        "i need gym", "where to find gym",
        "fitness center near me", "gym near me",
    ],

    # ──────────────────────────────────────────────────────────────────────────
    # SERVICES
    # ──────────────────────────────────────────────────────────────────────────
    "beautician": [
        # Core
        "beautician", "beauty", "beauty parlour", "parlour", "parlor",
        "salon", "hair", "haircut", "hair salon", "hair cut", "hair style",
        "blowdry", "blow dry", "barber", "grooming", "threading",
        "waxing", "facial", "cleanup", "makeup", "bridal makeup",
        "pedicure", "manicure", "nail art", "nail", "nails",
        "gel nails", "mehendi", "henna", "beauty treatment",
        "beauty center", "beauty shop", "ladies salon", "gents salon",
        "unisex salon", "hair colouring", "hair color", "hair spa",
        "keratin", "smoothening", "rebonding", "bleach", "detan",
        # Real job/service data
        "mens haircut", "men haircut", "mens combo", "ladies combo",
        "bridal facial", "makeup artist",
        # Store names
        "bevans beauty care",
        # Natural language
        "i need salon", "where is beauty parlour", "salon near me",
        "haircut shop", "beauty salon", "hair styling salon",
        "waxing salon", "bridal makeup", "nail art shop",
        "threading salon", "need haircut", "find salon",
        "beauty parlour near me", "haircut near me",
    ],

    "home services": [
        # Core
        "electrician", "electrical", "wiring", "electric repair",
        "carpenter", "carpentry", "furniture repair", "painter",
        "painting", "house painting", "cleaning", "housekeeping",
        "home repair", "home service", "maintenance", "handyman",
        "power cut", "short circuit", "socket repair",
        # Real data
        "water pump", "water pump repair", "motor repair",
        "inverter", "inverter battery", "battery", "e green battery",
        "electric work", "electrical work",
        # Natural language
        "i need electrician", "where to find electrician",
        "handyman near me", "home repair service", "painter needed",
        "need electrician", "find electrician",
        "electrical service near me", "home maintenance",
    ],

    "plumbing services": [
        # Core
        "plumber", "plumbing", "pipe repair", "pipe leak", "water pipe",
        "drainage", "tap repair", "bathroom plumbing", "pipeline",
        "water tank", "overhead tank",
        "bathroom leakage", "water leaking", "water leakage",
        "leak detector", "leak detectors",
        # Real data
        "trivandrum leak detectors", "apex plumbing solutions",
        "quickfix pipe", "safeflow plumbing",
        "pipe", "drainage issue", "tap", "faucet",
        # Natural language
        "i need plumber", "where to find plumber", "plumbing service",
        "plumbing near me", "find plumber", "need plumber",
        "drainage problem", "pipe burst", "water leakage service",
    ],

    "ac / tv services": [
        # Core — covers generic electrics/electrical repair queries too
        "electric", "electrics", "electrical repair", "electrical shop",
        "electronics repair", "home appliance repair",
        "ac repair", "ac service", "ac not working", "ac gas",
        "hvac", "split ac", "window ac", "ac gas filling", "ac cleaning",
        "ac installation", "ac technician", "ac not cooling",
        "tv repair", "television repair", "led repair", "tv service",
        "electronic repair", "air conditioning service",
        # Real data
        "ozone ac care", "aadhi ac", "venus electrical",
        "ac tv mechanic", "ac/tv mechanic",
        "fix my ac", "i need ac repair",
        "where to get ac fixed", "tv repair shop",
        "ac service center", "ac service near me",
        "tv repair near me", "led tv repair",
    ],

    "catering services": [
        "catering", "caterer", "food catering", "event catering",
        "function catering", "wedding catering", "party food",
        "bulk food", "catering service", "food for function",
        "food for event", "event food", "party catering",
        "caterring", "cater", "catring", "catering company",
        "ss caterers", "jayan catering", "catering services",
        "i need catering", "where to find caterer",
        "wedding catering", "party food catering",
        "need caterer", "find catering service",
    ],

    "constructors / engi": [
        # Core
        "construction", "contractor", "engineer", "building",
        "civil work", "architecture", "architect", "renovation",
        "house construction", "building contractor", "civil engineer",
        "construction company", "builder", "masonry", "flooring",
        "tiling", "waterproofing", "false ceiling", "interior contractor",
        # Real data
        "welding", "welding works", "welding service",
        "mk construction", "infiniti jesus homes", "kpn construction",
        "dennis construction", "arun installations",
        "cement", "steel rod", "paint", "construction material",
        "jcb", "jcb service", "lord jcb",
        "construction realstate", "construction & realstate",
        # Natural language
        "i need contractor", "where to find builder",
        "construction company", "renovation service",
        "house construction", "find builder", "need engineer",
        "civil contractor near me", "construction near me",
    ],

    "doctors": [
        # Core
        "doctor", "physician", "clinic", "medical", "health",
        "consultation", "checkup", "general physician",
        "hospital", "nursing home",
        "healthcare", "need a doctor", "doctor nearby",
        # Specialists
        "dentist", "dental", "eye doctor", "skin doctor",
        "dermatologist", "pediatrician", "child doctor",
        "gynecologist", "orthopedic", "cardiologist",
        "ent", "urologist", "neurologist",
        # Pharmacy
        "pharmacy", "chemist", "medical shop", "medicine shop",
        "drug store", "pharma", "chemist shop", "medical store",
        "need medicine", "buy medicine", "tablet", "prescription",
        # Real data
        "careplus family clinic", "metro pediatric",
        "elite ortho", "dr radhakrishnan", "kollam city health",
        "general hospital", "clinic near me",
        # Natural language
        "i need doctor", "where to find doctor",
        "clinic near me", "doctor appointment",
        "medical consultation", "find doctor",
        "hospital near me", "health center",
    ],

    "installations": [
        "installation", "install", "setup", "fitting", "mounting",
        "cctv installation", "water heater", "geyser", "fan fitting",
        "light fitting", "cctv", "security camera", "cctv setup",
        "dish tv installation", "set top box", "antenna",
        "cctv & automatic remote gate", "security system",
        "inverter installation", "solar installation",
        "i need installation", "where to find installer",
        "cctv near me", "installation service",
    ],

    "it $ services": [
        # Core
        "it", "software", "technology", "web development",
        "app development", "it company", "tech company", "digital",
        "software company", "it services", "website", "coding",
        "programming", "network", "it support",
        "information technology", "digital marketing", "seo",
        "social media marketing", "web design", "mobile app",
        "android app", "ios app",
        # Real data (from actual job/product data)
        "app development", "application developer", "app developer",
        "website development", "webdeveloper", "web developer",
        "web development full stack", "python full stack developer",
        "python developer", "python ai ml", "python full stack",
        "advanced python", "e commerce app", "mobile app development",
        "ui ux design", "ui ux", "uiux", "uiux designer",
        "poster design", "reels", "motion graphics",
        "animation", "vfx", "3dot vfx", "3dot academy",
        "boss app studio", "it services",
        "online works", "digital work",
        "graphic designer", "graphics", "graphic design",
        "social media", "content creation",
        # Natural language
        "i need it support", "where to find web developer",
        "tech support", "need developer", "find developer",
        "software company near me", "app development company",
        "web design company", "digital agency",
        "need website", "create website", "need app",
        "develop app", "develop website",
        "design poster", "design reel", "design banner",
        "creative agency", "design studio",
        "need designer", "find designer", "graphic work",
        "need it company", "it company near me",
    ],

    "photographer": [
        "photographer", "photography", "photo studio", "videography",
        "wedding photography", "portrait", "studio", "video shoot",
        "photo shoot", "camera man", "event photography",
        "candid photography", "pre wedding shoot", "birthday photography",
        "videographer", "fotographer", "fotography",
        # Real data
        "jass studio", "arputham maria", "arputham photographer",
        "camera service", "photo frame", "photo frames",
        "wedding invitation", "photos",
        # Natural language
        "i need photographer", "where to find photographer",
        "photography studio", "find photographer",
        "need photos", "wedding photographer",
        "event photographer", "photo studio near me",
    ],

    "real estate": [
        "real estate", "property", "flat", "apartment",
        "buy property", "plot", "pg", "paying guest",
        "property dealer", "property agent", "house for rent",
        "house for sale", "office space", "commercial property",
        "real estate agent", "land agent", "property consultant",
        "rooms lodges", "room",
        "need property", "buy flat", "rent apartment",
        "room for rent", "house rent", "i need property",
        "where to buy flat", "apartment for sale",
        "land for sale", "plot for sale",
        "real estate near me", "property near me",
        "nagercoil nilam", "real estate company",
    ],

    "used vehicles": [
        "used vehicle", "second hand vehicle", "old car", "used car",
        "second hand bike", "old bike", "pre owned", "buy used vehicle",
        "used automobile", "second hand", "second hand car",
        "used bike", "old vehicle", "pre owned car",
        "refurbished vehicle", "vel murugan vehicles",
        "i need used car", "where to buy second hand vehicle",
        "pre owned car", "old car dealer", "used car dealer",
        "second hand vehicle dealer",
    ],

    # ──────────────────────────────────────────────────────────────────────────
    # AUTOMOBILES
    # ──────────────────────────────────────────────────────────────────────────
    "bike & car servicing": [
        # Core
        "car service", "car repair", "garage", "auto repair",
        "vehicle service", "car wash", "denting painting",
        "car mechanic", "mechanic", "bike service", "bike repair",
        "two wheeler", "motorcycle", "scooter repair", "puncture",
        "puncher", "bike mechanic", "automobile service", "vehicle repair",
        "car servicing", "bike servicing", "vehicle maintenance",
        "tyre change", "battery change", "engine repair", "oil change",
        # Real data
        "arjun bike car servicing", "bullet classic 350 service",
        "car ac", "car air conditioning", "car polish",
        "car polish & service", "car accessories service",
        "car wash near me", "garage near me",
        # Natural language
        "i need car service", "where to get car repaired",
        "bike service center", "oil change service",
        "find mechanic", "need mechanic", "car broke down",
        "two wheeler service", "motorcycle repair",
    ],

    "bike & car selling": [
        # Core
        "buy car", "sell car", "new car", "car showroom", "bike showroom",
        "buy bike", "sell bike", "vehicle showroom", "new vehicle",
        "new bike", "car dealer", "bike dealer",
        # Real data
        "river bikes", "aaro motors", "river indie gen 3",
        "new bike showroom", "bike shop",
        # Natural language
        "want to buy a car", "buy a car", "looking to buy car",
        "purchase car", "new car showroom", "buy a bike",
        "car purchase", "bike purchase", "new automobile",
        "car buying", "bike buying", "vehicle dealer",
        "i need to buy car", "where to buy car",
        "car showroom near me", "buy new bike",
        "second hand car dealer", "looking to buy vehicle",
    ],

    "automobiles accessories": [
        "car accessories", "bike accessories", "auto accessories",
        "vehicle accessories", "spare parts", "car battery",
        "bike parts", "auto parts", "car seat cover", "steering cover",
        "e green battery service", "wash factory",
        "i need car accessories", "where to buy spare parts",
        "auto accessories shop", "car spare parts",
        "bike spare parts", "vehicle spare parts",
    ],

    # ──────────────────────────────────────────────────────────────────────────
    # TRANSPORTATION SERVICES
    # ──────────────────────────────────────────────────────────────────────────
    "taxi": [
        # Core
        "taxi", "cab", "local taxi", "city taxi", "local cab",
        "local ride", "daily commute", "city ride",
        "need a ride", "local transport", "drop", "pick up",
        "local travel", "cab nearby", "taxi service",
        "taxi driver", "airport pickup", "airport taxi",
        "airport drop", "airport transfer",
        # Real data
        "ajin taxi", "vijay taxi", "tatchanya taxi", "aruthra tours",
        "js cab", "aravind taxi", "anish kumar taxi",
        "call taxi", "taxi service nearby",
        "cab for local travel", "local cab service",
        # Real user queries
        "i need taxi", "where to get taxi", "taxi near me",
        "find taxi", "need cab", "need taxi",
        "book taxi", "taxi booking", "cab booking",
        "taxi available near me", "find taxi available",
    ],

    "auto rickshaw": [
        # Core
        "auto", "auto rickshaw", "autorickshaw", "three wheeler",
        "tuk tuk", "auto driver", "rickshaw", "auto for hire",
        "auto nearby", "auto service", "e rickshaw", "electric auto",
        "share auto", "passenger auto",
        # Real data
        "jonnah auto", "babu auto", "suthakar auto",
        "m kathiravan auto", "mikel louis auto", "sivan auto",
        "kgkulam auto", "ashvika auto", "majin dhas auto",
        "auto near me", "find auto",
        # Tamil
        "கோகுலம் ஆட்டோ",
        # Natural language
        "i need auto", "where to get auto", "auto near me",
        "need auto for commute", "find auto rickshaw",
        "book auto", "auto available near me",
        "i need auto richskaw", "auto richskaw",  # typo from real logs
    ],

    "tourist bus": [
        # Core
        "tourist bus", "tour bus", "bus hire", "bus rental",
        "group travel", "charter bus", "trip bus", "minibus",
        "bus for function", "bus for trip", "bus for tour",
        "travel bus", "ksrtc", "ac bus", "sleeper bus", "coach",
        "tourist van", "tempo traveller", "tempotraveller",
        # Real data
        "emar cabs", "matha travels", "sri krishna travels",
        "suja travels", "selin travels",
        # Natural language
        "i need bus", "where to book bus", "tour bus service",
        "bus rental near me", "group travel bus", "trip bus near me",
        "need tourist bus", "find tourist bus",
    ],

    "load vehicles": [
        # Core
        "shift my house",
        "shift house",
        "shifting my home", 
        "need to shift my house",
        "i need to shift",
        "house shifting",
        "home shifting",
        "furniture shifting",
        "shifting service",
        "load vehicle", "goods vehicle", "truck", "lorry", "mini truck",
        "tempo", "house shifting", "shifting", "transport goods",
        "goods transport", "cargo", "packers movers", "moving",
        "vehicle for shifting", "furniture shifting",
        "packers and movers", "shifting service",
        # Real data
        "juwana transport", "malar load vehicles", "rajesh travels load",
        "saraswati load vehicle", "ajith load", "vasahan load",
        "lord jcb services",
        "tata ace", "tata intra", "fast transport service",
        "aravind transport", "transport", "transportation",
        # Natural language
        "shift my house", "need to shift", "house shift",
        "home shifting", "i need to shift my house",
        "shifting my home", "move my furniture", "need to move",
        "help with shifting", "need a truck for shifting",
        "lorry for shifting", "shift house", "shifting furniture",
        "i need truck", "where to get truck", "shifting services",
        "need to shift house", "moving service", "lorry for hire",
        "goods transport", "furniture moving",
        "find load vehicles near me",
    ],

    "bike taxi": [
        "bike taxi", "bike ride", "two wheeler taxi", "rapido",
        "bike cab", "i need bike taxi", "where to get bike ride",
        "bike taxi service", "two wheeler cab",
    ],

    "vehicle rental": [
        "vehicle rental", "rent vehicle", "self drive", "rent a car",
        "hire vehicle", "car on rent", "bike on rent", "rent a bike",
        "car hire", "self driven car", "rent car",
        "i need to rent car", "where to rent vehicle",
        "car on rent near me", "vehicle rental near me",
    ],

    # ──────────────────────────────────────────────────────────────────────────
    # TRAVEL & HOSPITALITY
    # ──────────────────────────────────────────────────────────────────────────
    "flight": [
        "flight", "airline", "air ticket", "flight booking",
        "airways", "plane ticket", "domestic flight",
        "international flight", "i need flight ticket",
        "where to book flight", "airline booking",
        "fly", "air travel",
    ],

    "train": [
        "train", "railway", "irctc", "train ticket", "rail",
        "train booking", "i need train ticket", "where to book train",
        "railway booking", "local train",
    ],

    "bus": [
        "bus ticket", "long distance bus", "bus booking",
        "intercity bus", "i need bus ticket", "where to book bus",
        "bus booking service", "bus travel",
    ],

    "cabs": [
        "cab", "outstation cab", "airport cab", "outstation taxi",
        "long distance cab", "intercity cab", "outstation travel",
        "i need cab", "where to get cab", "outstation cab",
        "airport cab", "long distance cab", "inter city travel",
    ],

    "holidays": [
        "holiday", "tour package", "vacation", "trip package",
        "travel package", "honeymoon package", "holiday package",
        "weekend trip", "tour operator", "holidays offer",
        "i need holiday package", "where to find tour package",
        "vacation planning", "trip booking", "tour",
    ],

    "luxury resorts": [
        "resort", "luxury resort", "5 star", "luxury stay",
        "premium hotel", "5 star hotel", "luxury hotel",
        "i need resort", "where to find luxury hotel",
        "resort booking", "premium resort",
    ],

    "lodges": [
        "lodge", "lodging", "budget stay", "inn", "guest house",
        "cheap hotel", "room", "accommodation", "hotel stay",
        "budget hotel", "dharamshala", "room for rent",
        "rooms lodges", "rooms / lodges",
        "i need lodge", "where to book room",
        "budget hotel near me", "hotel near me",
        "lodge near me", "need room", "find lodge",
    ],

    # ──────────────────────────────────────────────────────────────────────────
    # OTHERS
    # ──────────────────────────────────────────────────────────────────────────
    "education": [
        # Core
        "education", "coaching", "tuition", "classes", "tutor",
        "study", "academic", "school coaching", "entrance coaching",
        "neet", "jee", "upsc", "learning", "institute", "academy",
        "training", "course", "coaching center", "coaching centre",
        "tutorial", "spoken english", "abacus",
        # Real data
        "i-tech software academy", "karka ai tech academy",
        "3 dot academy", "3dot accademy",
        "stella mary's college", "scott christian college",
        "ai python course", "python full stack course",
        "ai & python course", "coding courses", "non coding courses",
        "web development full stack course",
        "advanced python ai ml full stack course",
        "ui ux design course",
        # Natural language
        "i need coaching", "where to find tuition",
        "coaching class near me", "training center", "class near me",
        "find coaching", "need classes", "education near me",
    ],

    "fitness others": [
        "fitness", "gym", "workout", "exercise", "weight training",
        "yoga", "zumba", "aerobics", "crossfit", "health club",
        "bodybuilding", "treadmill", "fitness center", "fitness centre",
        "gym center", "gym nearby", "yoga center", "yoga class",
        "pilates", "gym membership", "fitness trainer",
        "yoga studio", "workout center",
        "carmel fitness centre", "ds fitness center",
        "i need gym", "where to find gym",
        "fitness center near me", "gym near me",
    ],

    "pet care": [
        "pet", "pet shop", "dog", "cat", "fish", "bird", "pet food",
        "pet accessories", "aquarium", "vet", "veterinary",
        "animal doctor", "pet doctor", "pet store", "dog food",
        "cat food", "dog grooming", "pet clinic",
        "re goat form", "goat", "jamunapuri goat", "goats",
        "i need pet shop", "where to find vet",
        "pet doctor near me", "veterinary clinic", "pet grooming",
    ],

    "meat & poultry": [
        "meat", "chicken", "mutton", "fish", "seafood", "non veg",
        "butcher", "poultry", "egg", "meat shop", "chicken shop",
        "broiler", "fresh meat", "poultry shop", "fish shop",
        "prawn", "crab", "beef",
        "sana mutton & broilers", "niyaz chicken",
        "karuvaadu", "dry fish", "netholi",
        "need meat", "buy meat", "chicken near me",
        "mutton shop", "fish shop near me",
    ],

    "art & graft": [
        "art", "craft", "drawing", "painting class", "art studio",
        "creative", "design studio", "animation", "vfx",
        "art and craft", "art class",
        "poster", "reels", "motion graphics",
        "premium posters", "motion graphics artist",
        "artist", "graphic artist", "creative artist",
        "i need artist", "find artist near me",
        "need poster design", "poster maker",
        "create posters", "create reels",
    ],

    "freelance and gig": [
        "freelance", "freelancer", "gig", "part time", "work from home",
        "remote work", "contract work", "freelance work",
        "i need freelancer", "find freelancer",
        "gig worker", "part time job",
    ],

    "legal and consulting": [
        "lawyer", "advocate", "legal", "court", "case", "legal advice",
        "attorney", "solicitor", "consulting", "consultant", "advisor",
        "ca", "chartered accountant", "accountant", "tax", "gst",
        "gst filing", "income tax", "legal consultant",
        "property lawyer", "criminal lawyer", "divorce lawyer",
        "legal firm", "law firm", "property dispute",
        "i need lawyer", "where to find advocate",
        "legal consultation", "property lawyer near me",
        "tax consultant near me", "ca near me",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY SYNONYM MAP  (broad — level 2 fallback)
# ═══════════════════════════════════════════════════════════════════════════════

CATEGORY_SYNONYM_MAP: dict[str, list[str]] = {
    "food & dining": [
        "food", "eat", "hungry", "restaurant", "dining", "meal",
        "biryani", "biriyani", "cafe", "bakery", "juice", "snacks",
        "tiffin", "dhaba", "something to eat", "need food",
        "coffee", "tea shop", "hotel", "mess", "canteen",
        "shawarma", "burger", "pizza", "idly", "dosa",
        "lunch", "dinner", "breakfast",
    ],
    "fashions": [
        "fashion", "clothes", "clothing", "dress", "outfit",
        "apparel", "garment", "wear", "shoes", "footwear",
        "jewellery", "accessories", "bag", "watch", "sunglass",
        "saree", "kurta", "salwar", "jeans", "shirt",
    ],
    "services": [
        "service", "repair", "fix", "plumber", "electrician",
        "doctor", "beautician", "catering", "construction",
        "photographer", "it", "software", "legal", "real estate",
        "lawyer", "advocate", "ca", "handyman", "professional",
        "welding", "carpenter",
    ],
    "transportation services": [
        "transport", "ride", "taxi", "auto", "truck", "lorry",
        "shift", "move", "cab", "local travel", "commute",
        "vehicle", "cargo", "auto rickshaw", "rickshaw",
        "shifting", "goods", "load",
    ],
    "mobiles & electronics": [
        "mobile", "phone", "electronics", "gadget", "laptop",
        "computer", "tablet", "earphone", "speaker", "camera",
        "smart watch", "charger", "electronic",
    ],
    "home & living furnitures": [
        "furniture", "sofa", "bed", "kitchen", "decor",
        "interior", "wood", "cupboard", "mattress", "towel",
        "timbers", "carpenter",
    ],
    "grocery,beauty & health": [
        "grocery", "vegetable", "fruit", "kirana", "supermarket",
        "beauty", "health", "pharmacy", "medicine", "personal care",
        "chemist", "medical shop", "snacks", "chips", "muruku",
        "dry fruits", "cashew",
    ],
    "automobiles": [
        "car", "bike", "vehicle", "automobile", "motor", "mechanic",
        "garage", "two wheeler", "four wheeler", "spare parts",
        "car service", "bike service", "puncher", "puncture",
    ],
    "electrical appliances": [
        "appliance", "fridge", "washing machine", "television",
        "microwave", "electrical shop", "home appliance",
        "tv", "ac shop", "fan shop",
    ],
    "entertainment": [
        "entertainment", "movie", "cinema", "theatre", "event",
        "concert", "sports", "game", "fun", "amusement park",
        "morning show", "4k theatre",
    ],
    "gifts & jewels": [
        "gift", "jewellery", "jewelry", "flower", "toy", "present",
        "gold", "silver", "bouquet",
    ],
    "sports products": [
        "sports equipment", "gym equipment", "fitness equipment",
        "cricket", "football", "sports shop", "protein", "supplement",
        "badminton",
    ],
    "travel & hospitality": [
        "travel", "hotel", "lodge", "resort", "holiday", "tour",
        "trip", "flight", "train", "stay", "accommodation",
        "outstation", "airport", "vacation", "rooms",
    ],
    "books & stationery": [
        "book", "stationery", "pen", "notebook", "school supplies",
        "novel", "textbook",
    ],
    "others": [
        "education", "fitness", "gym", "pet", "meat", "legal", "art",
        "freelance", "academy", "institute", "coaching", "yoga",
        "lawyer", "vet", "chicken", "goat", "artist",
        "animation", "vfx", "poster",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# NORMALISATION
# ═══════════════════════════════════════════════════════════════════════════════

def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


CONCEPT_PRIORITY = {
    "meat & poultry":               10,
    "real estate":    2, 
    "automobiles accessories":       10,
    "mobiles & electronics accessories": 10,
    "bags & accessories":            5,
    "restaurent":                    3,   # "chicken" should NOT hit here first
}

# ── Build reverse index: normalised synonym → internal concept key ────────────
_REVERSE_INDEX: dict[str, str] = {}
for _concept, _synonyms in SYNONYM_MAP.items():
    _REVERSE_INDEX[_normalize(_concept)] = _concept
    for _syn in _synonyms:
        _key = _normalize(_syn)
        if _key in _REVERSE_INDEX:
            existing = _REVERSE_INDEX[_key]
            existing_priority = CONCEPT_PRIORITY.get(existing, 0)
            new_priority      = CONCEPT_PRIORITY.get(_concept, 0)
            if new_priority > existing_priority:
                logger.debug(
                    f"Collision: '{_key}' → replacing '{existing}' "
                    f"(priority {existing_priority}) with '{_concept}' "
                    f"(priority {new_priority})"
                )
                _REVERSE_INDEX[_key] = _concept
            else:
                logger.debug(
                    f"Collision: '{_key}' → keeping '{existing}', "
                    f"dropping '{_concept}'"
                )
        else:
            _REVERSE_INDEX[_key] = _concept

# ── Build reverse index for categories ───────────────────────────────────────
_CAT_REVERSE_INDEX: dict[str, str] = {}
for _concept, _synonyms in CATEGORY_SYNONYM_MAP.items():
    _CAT_REVERSE_INDEX[_normalize(_concept)] = _concept
    for _syn in _synonyms:
        _key = _normalize(_syn)
        if _key not in _CAT_REVERSE_INDEX:
            _CAT_REVERSE_INDEX[_key] = _concept


# ═══════════════════════════════════════════════════════════════════════════════
# CORE MATCHING HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _concept_from_text(text: str, reverse_index: dict) -> Optional[str]:
    """
    Free-form text → best matching internal concept key.
    Resolution order:
      1. Ambiguous word context check (hotel, chicken etc.)
      2. Exact phrase match
      3. Multi-word partial phrase match (longest wins)
      4. Individual word match (longest wins, min len 2)
      5. Substring match (len ≥ 4, longest wins)
      6. Fuzzy match (threshold 0.75)
    """
    norm = _normalize(text)
    if not norm:
        return None

    words = set(norm.split())

    # ── 1. Ambiguous word context check ──────────────────────────────────────
    # Some words genuinely mean different things depending on surrounding words.
    # Check context before falling into the reverse index.
    AMBIGUOUS_CONTEXT = {
    "hotel": {
        "stay_hints":  {"stay", "room", "night", "lodge", "book", "accommodation", "rent"},
        "food_hints":  {"eat", "food", "biryani", "lunch", "dinner", "meals", "dine"},
        "stay_result": "lodges",
        "food_result": "restaurent",
        "default":     "restaurent",
    },                  # ← ADD THIS closing brace
    "gym": {
                "equipment_hints": {"equipment", "buy", "treadmill", "dumbbell", "shop"},
                "visit_hints":     {"near me", "nearby", "join", "membership", "class",
                                    "center", "centre", "find"},
                "equipment_result": "sports products",
                "visit_result":     "fitness sports",   # or "fitness others"
                "default":          "fitness sports",   # most common intent
            },
        
    "chicken": {
            "shop_hints":  {"shop", "buy", "fresh", "raw", "broiler", "kg", "meat", "poultry"},
            "food_hints":  {"biryani", "restaurant", "hotel", "eat", "food", "fry", "curry"},
            "shop_result": "meat & poultry",
            "food_result": "restaurent",
            "default":     "meat & poultry",  # "chicken shop" → meat, not restaurant
        },
    "accessories": {
            "mobile_hints": {"mobile", "phone", "charger", "cable", "cover", "screen"},
            "auto_hints":   {"car", "bike", "vehicle", "auto", "spare"},
            "fashion_hints":{"bag", "watch", "belt", "fashion", "ladies", "mens"},
            "mobile_result":"mobiles & electronics accessories",
            "auto_result":  "automobiles accessories",
            "fashion_result":"bags & accessories",
            "default":      "bags & accessories",
        },
    "bus": {
            "ticket_hints": {"ticket", "booking", "intercity", "long", "distance"},
            "tour_hints":   {"tour", "trip", "hire", "rental", "group", "charter"},
            "ticket_result":"bus",
            "tour_result":  "tourist bus",
            "default":      "tourist bus",
        },
    "sports": {
            "shop_hints":   {"shop", "equipment", "gear", "buy", "bat", "ball"},
            "watch_hints":  {"watch", "match", "game", "ticket", "event", "stadium"},
            "shop_result":  "sports products",
            "watch_result": "sports entertainment",
            "default":      "sports products",
        },
    }

    for ambiguous_word, ctx in AMBIGUOUS_CONTEXT.items():
        if ambiguous_word in words:
            # Check each hint group in priority order
            for hint_key in ["stay_hints", "shop_hints", "mobile_hints",
                             "auto_hints", "ticket_hints", "tour_hints",
                             "watch_hints", "food_hints", "fashion_hints"]:
                if words & ctx.get(hint_key, set()):
                    result_key = hint_key.replace("_hints", "_result")
                    result     = ctx.get(result_key)
                    if result:
                        logger.debug(
                            f"Ambiguous '{ambiguous_word}' in '{text}' → "
                            f"context hint '{hint_key}' → '{result}'"
                        )
                        return result
            # No context clues found — use default
            logger.debug(
                f"Ambiguous '{ambiguous_word}' in '{text}' → "
                f"no context, using default '{ctx['default']}'"
            )
            return ctx["default"]

    # ── 2. Exact phrase match ─────────────────────────────────────────────────
    if norm in reverse_index:
        logger.debug(f"Exact match: '{norm}' → '{reverse_index[norm]}'")
        return reverse_index[norm]

    # ── 3. Multi-word partial phrase match (longest wins) ────────────────────
    # Tries all sub-phrases of the input to catch "need auto rickshaw near me"
    # matching "auto rickshaw" before just "auto"
    word_list = norm.split()
    best_phrase_match, best_phrase_len = None, 0

    for size in range(len(word_list), 1, -1):           # from longest to shortest
        for start in range(len(word_list) - size + 1):
            phrase = " ".join(word_list[start:start + size])
            if phrase in reverse_index and len(phrase) > best_phrase_len:
                best_phrase_match = reverse_index[phrase]
                best_phrase_len   = len(phrase)

    if best_phrase_match:
        logger.debug(f"Phrase match: '{norm}' → '{best_phrase_match}'")
        return best_phrase_match

    # ── 4. Individual word match (longest wins, min len 2) ───────────────────
    # Min len 2 so "ac", "tv", "bus" all match correctly
    best_word_match, best_word_len = None, 0
    for word in word_list:
        if len(word) >= 2 and word in reverse_index and len(word) > best_word_len:
            best_word_match = reverse_index[word]
            best_word_len   = len(word)
    if best_word_match:
        logger.debug(f"Word match: '{norm}' → '{best_word_match}'")
        return best_word_match

    # ── 5. Substring match (phrase len ≥ 4 to avoid noise) ──────────────────
    # "restourant" contains "resto" which is close to "restaurent"
    best_sub_match, best_sub_len = None, 0
    for syn, concept in reverse_index.items():
        if len(syn) >= 4 and (syn in norm or norm in syn):
            if len(syn) > best_sub_len:
                best_sub_match = concept
                best_sub_len   = len(syn)
    if best_sub_match:
        logger.debug(f"Substring match: '{norm}' → '{best_sub_match}'")
        return best_sub_match

    # ── 6. Fuzzy match (threshold 0.75) ──────────────────────────────────────
    # Last resort — catches typos like "restourant", "auto richskaw"
    # Only runs against synonyms of reasonable length to avoid false positives
    best_concept, best_score = None, 0.75
    for syn, concept in reverse_index.items():
        if len(syn) < 4:                                # skip very short synonyms
            continue
        # Only fuzzy match if lengths are in a reasonable range of each other
        length_ratio = min(len(norm), len(syn)) / max(len(norm), len(syn))
        if length_ratio < 0.5:                          # too different in length
            continue
        score = difflib.SequenceMatcher(None, norm, syn).ratio()
        if score > best_score:
            best_score   = score
            best_concept = concept

    if best_concept:
        logger.debug(f"Fuzzy match: '{norm}' → '{best_concept}' (score={best_score:.2f})")

    return best_concept


def _match_concept_to_db(concept: str, available: List[str]) -> str:
    """
    Internal concept key → exact DB name from available list.
    Resolution: exact (case-insensitive) → substring → fuzzy (≥0.65)
    """
    if not concept or not available:
        return ""

    norm_concept = _normalize(concept)

    # 1 — exact
    for item in available:
        if _normalize(item) == norm_concept:
            return item

    # 2 — substring
    for item in available:
        norm_item = _normalize(item)
        if norm_concept in norm_item or norm_item in norm_concept:
            return item

    # 3 — fuzzy
    best_item, best_score = "", 0.65
    for item in available:
        score = difflib.SequenceMatcher(None, norm_concept, _normalize(item)).ratio()
        if score > best_score:
            best_score = score
            best_item  = item

    return best_item


def _resolve_db_name(concept: str, available: List[str]) -> str:
    """
    Resolve internal concept key to exact DB name.
    Uses DB_SUBCAT_NAMES canonical lookup first, then fuzzy fallback.
    """
    canonical = DB_SUBCAT_NAMES.get(concept) or DB_CAT_NAMES.get(concept)
    if canonical:
        for item in available:
            if item == canonical or _normalize(item) == _normalize(canonical):
                return item

    return _match_concept_to_db(concept, available)


# ═══════════════════════════════════════════════════════════════════════════════
# AI FALLBACK
# ═══════════════════════════════════════════════════════════════════════════════

def _ai_category_fallback(
    user_text: str,
    available_categories: List[str],
    groq_client,
) -> str:
    """Call Groq AI to pick the best category when local matching fails."""
    try:
        cat_list = ", ".join(available_categories[:80])
        prompt = (
            f"Available shop categories: {cat_list}\n\n"
            f"User is looking for: \"{user_text}\"\n\n"
            "Which ONE category from the list best matches what the user wants? "
            "Reply with ONLY the exact category name from the list, nothing else. "
            "If nothing matches, reply with exactly: NONE"
        )
        response = groq_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=30,
            temperature=0,
            timeout=8,
        ).choices[0].message.content.strip()

        if response and response.upper() != "NONE":
            for cat in available_categories:
                if cat.lower() == response.lower():
                    return cat
            best = _match_concept_to_db(response, available_categories)
            if best:
                return best

    except Exception as e:
        logger.warning(f"AI category fallback failed: {e}")

    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def get_semantic_category(user_text: str, available_categories: List[str]) -> str:
    """
    Map free-form user text to the best matching DB subcategory name.
    Single-level lookup (subcategory only).
    """
    if not user_text or not available_categories:
        return ""

    concept = _concept_from_text(user_text, _REVERSE_INDEX)
    logger.info(f"[concept_from_text] '{user_text}' → concept='{concept}'") 
    if not concept:
        return ""

    return _resolve_db_name(concept, available_categories)


def get_semantic_category_two_level(
    user_text: str,
    subcategories: List[str],
    categories: List[str],
    groq_client=None,
) -> str:
    """
    Two-level semantic matching.

    Level 1 — Subcategory  (e.g. "Restaurent", "Taxi", "Auto Rickshaw")
    Level 2 — Category     (e.g. "Food & Dining", "Transportation Services")

    For each level: local synonym map → fuzzy → Groq AI fallback.
    Returns the matched DB name string, or "" if nothing found.
    """
    if not user_text:
        return ""

    # ── Level 1: Subcategory ──────────────────────────────────────────────────
    concept = _concept_from_text(user_text, _REVERSE_INDEX)
    if concept:
        matched = _resolve_db_name(concept, subcategories)
        if matched:
            logger.info(f"[subcategory] '{user_text}' → '{matched}'")
            return matched

    # AI fallback for subcategory
    if groq_client and subcategories:
        ai_result = _ai_category_fallback(user_text, subcategories, groq_client)
        if ai_result:
            logger.info(f"[AI subcategory] '{user_text}' → '{ai_result}'")
            return ai_result

    # ── Level 2: Parent Category ──────────────────────────────────────────────
    if categories:
        cat_concept = _concept_from_text(user_text, _CAT_REVERSE_INDEX)
        if cat_concept:
            matched_cat = _resolve_db_name(cat_concept, categories)
            if matched_cat:
                logger.info(f"[category] '{user_text}' → '{matched_cat}'")
                return matched_cat

        if groq_client:
            ai_cat = _ai_category_fallback(user_text, categories, groq_client)
            if ai_cat:
                logger.info(f"[AI category] '{user_text}' → '{ai_cat}'")
                return ai_cat

    logger.debug(f"No match found for '{user_text}'")
    return ""


def get_semantic_category_with_ai_fallback(
    user_text: str,
    available_categories: List[str],
    groq_client=None,
) -> str:
    """Backward-compatible single-level wrapper."""
    result = get_semantic_category(user_text, available_categories)
    if result:
        return result
    if groq_client and available_categories:
        return _ai_category_fallback(user_text, available_categories, groq_client)
    return ""


def get_category_synonyms(subcategory_name: str) -> List[str]:
    """Return all synonyms for a given DB subcategory name."""
    if not subcategory_name:
        return []
    norm = _normalize(subcategory_name)
    if norm in SYNONYM_MAP:
        return SYNONYM_MAP[norm]
    concept = _concept_from_text(subcategory_name, _REVERSE_INDEX)
    if concept and concept in SYNONYM_MAP:
        return SYNONYM_MAP[concept]
    return []