"""
Generate realistic user queries based on actual DB categories & subcategories
"""

QUERIES_BY_CATEGORY = {
    # 1. Fashions
    "Fashions": {
        "Clothing": [
            "i need clothes", "where to buy clothes", "clothing shop near me",
            "i need new dress", "where can i get clothes", "clothing store",
            "need outfit for party", "shop for dress", "buy new clothes",
            "good clothing store", "ethnic wear shop", "designer clothes",
        ],
        "Footwear": [
            "i need shoes", "where to buy shoes", "shoe shop near me",
            "need new sandals", "footwear store", "buy shoes online",
            "shoe store nearby", "good footwear shop", "sports shoes",
        ],
        "Watch & Sunglass": [
            "i need watch", "where to buy watch", "sunglass shop",
            "need sunglasses", "watch store", "eyewear shop",
        ],
        "Bags & Accessories": [
            "i need bag", "where to buy bag", "bag shop",
            "need handbag", "accessories store", "leather bag shop",
        ],
    },

    # 2. Food & Dining
    "Food & Dining": {
        "Restaurent": [
            "i am hungry", "i need food", "where can i get food",
            "where to eat", "good restaurant near me", "place to eat",
            "i need biryani", "need restaurant", "where is food shop",
            "looking for restaurant", "best restaurant nearby",
            "food place nearby", "give me restaurants", "give me food",
            "something to eat", "need a restaurant", "where to find food",
            "dinner place", "lunch restaurant", "breakfast place",
            "non veg restaurant", "veg restaurant", "south indian food",
        ],
        "Drinks & Beverages": [
            "i need juice", "where to buy juice", "juice shop near me",
            "need fresh juice", "cold drinks", "juice bar", "coffee shop",
            "tea shop near me", "beverage shop", "smoothie place",
        ],
        "Bakery": [
            "i need bakery", "where to buy cake", "bakery near me",
            "bread shop", "cake shop", "pastry shop", "good bakery",
        ],
    },

    # 3. Home & Living Furnitures
    "Home & Living Furnitures": {
        "Furniture & Decor": [
            "i need furniture", "where to buy furniture", "furniture shop",
            "sofa shop near me", "bed shop", "wooden furniture",
            "furniture store", "home decor shop", "interior furniture",
        ],
        "Bed & Bath": [
            "i need bed", "where to buy mattress", "bed sheet shop",
            "bathroom accessories", "towel shop",
        ],
        "Kitchen & Dining": [
            "i need utensils", "where to buy cookware", "kitchen shop",
            "dining table", "kitchen accessories", "vessels shop",
        ],
    },

    # 4. Grocery,Beauty & Health
    "Grocery,Beauty & Health": {
        "Staples": [
            "i need groceries", "where to buy groceries", "grocery shop",
            "kirana shop near me", "supermarket", "need rice and dal",
            "where can i get groceries", "provision store", "daily needs",
            "buy groceries", "grocery store nearby", "vegetables and fruits",
        ],
        "Vegitables": [
            "i need vegetables", "where to buy vegetables", "vegetable shop",
            "fresh vegetables", "fruit shop", "vegetable market",
        ],
        "Personal & Baby Care": [
            "i need baby care", "where to buy baby products", "cosmetics shop",
            "personal care products", "skincare shop",
        ],
        "Household Care": [
            "i need cleaning products", "where to buy detergent",
            "household items shop", "cleaning supplies",
        ],
    },

    # 5. Mobiles & Electronics
    "Mobiles & Electronics": {
        "Mobiles": [
            "i need mobile", "where to buy phone", "mobile shop near me",
            "smartphone shop", "phone store", "buy mobile phone",
            "mobile repair", "phone service center",
        ],
        "Computers": [
            "i need laptop", "where to buy laptop", "computer shop",
            "laptop store near me", "desktop computer", "computer service",
        ],
        "Tablets": [
            "i need tablet", "where to buy tablet", "ipad shop",
        ],
        "Headphones & Speakers": [
            "i need headphones", "where to buy speaker", "earphone shop",
            "bluetooth speaker", "headphone store",
        ],
        "Camera": [
            "i need camera", "where to buy dslr", "camera shop",
            "photography camera", "camera store nearby",
        ],
    },

    # 6. Automobiles
    "Automobiles": {
        "Bike & Car Servicing": [
            "i need car service", "where to get car repaired", "garage near me",
            "bike service center", "car wash", "car mechanic",
            "bike repair shop", "auto repair", "vehicle maintenance",
            "car service nearby", "bike servicing", "oil change service",
        ],
        "Bike & Car Selling": [
            "i need to buy car", "where to buy car", "car showroom near me",
            "bike shop", "buy new bike", "second hand car", "used bike",
            "vehicle dealer", "buy a car", "looking to buy vehicle",
        ],
        "Accessories": [
            "i need car accessories", "where to buy spare parts",
            "auto accessories shop",
        ],
    },

    # 7. Services
    "Services": {
        "Beautician": [
            "i need salon", "where is beauty parlour", "salon near me",
            "haircut shop", "beauty salon", "hair styling", "waxing salon",
            "bridal makeup", "nail art shop", "threading salon",
        ],
        "Home Services": [
            "i need plumber", "where to find electrician", "handyman near me",
            "home repair service", "painter needed",
        ],
        "Plumbing Services": [
            "i need plumber", "where to find plumber", "plumbing service",
            "pipe repair", "water leakage", "drainage issue",
        ],
        "Ac / Tv Services": [
            "i need ac repair", "where to get ac fixed", "tv repair shop",
            "ac service center", "electronic repair",
        ],
        "catering Services": [
            "i need catering", "where to find caterer", "food catering service",
            "wedding catering", "party food catering",
        ],
        "constructors / Engi": [
            "i need contractor", "where to find builder", "construction company",
            "renovation service", "house construction",
        ],
        "Photographer": [
            "i need photographer", "where to find photographer", "photography studio",
            "wedding photography", "portrait photographer", "photo shoot",
        ],
        "Real estate": [
            "i need property", "where to buy flat", "real estate agent",
            "house for rent", "apartment for sale", "property dealer",
        ],
        "Used vehicles": [
            "i need used car", "where to buy second hand vehicle",
            "pre owned car", "old car dealer",
        ],
        "Doctors": [
            "i need doctor", "where to find doctor", "clinic near me",
            "hospital", "physician", "doctor appointment", "medical consultation",
        ],
        "Legal and Consulting": [
            "i need lawyer", "where to find advocate", "legal advice",
            "property lawyer", "legal consultation",
        ],
        "IT $ Services": [
            "i need it support", "where to find web developer", "software company",
            "tech support", "app development",
        ],
    },

    # 8. Transportation Services
    "Transportation Services": {
        "Taxi": [
            "i need taxi", "where to get taxi", "taxi near me",
            "call taxi", "need a ride", "local taxi",
            "taxi service nearby", "cab for local travel", "airport taxi",
        ],
        "Auto Rickshaw": [
            "i need auto", "where to get auto", "auto near me",
            "auto rickshaw", "need auto for commute", "three wheeler",
            "auto service", "auto for daily travel",
        ],
        "Load Vehicles": [
            "i need truck", "where to get truck", "shifting services",
            "need to shift house", "moving service", "lorry for hire",
            "goods transport", "shifting my home", "furniture moving",
        ],
        "Tourist Bus": [
            "i need bus", "where to book bus", "tour bus service",
            "bus rental", "group travel", "trip bus",
        ],
        "Bike Taxi": [
            "i need bike taxi", "where to get bike ride", "bike taxi service",
        ],
        "Vehicle Rental": [
            "i need to rent car", "where to rent vehicle", "self drive",
            "car on rent", "vehicle rental",
        ],
        "Cabs": [
            "i need cab", "where to get cab", "outstation cab",
            "airport cab", "long distance cab",
        ],
    },

    # 9. Entertainment
    "Entertainment": {
        "Movies": [
            "i need movie ticket", "where is cinema", "movie theatre near me",
            "movie show", "cinema booking",
        ],
        "Events": [
            "i need event", "where to find concert", "event tickets",
        ],
        "Sports": [
            "i need sports equipment", "where to buy sports gear",
            "sports shop", "gym equipment",
        ],
        "Theme Parks": [
            "i need theme park", "where is amusement park",
            "fun park nearby", "water park",
        ],
    },

    # 10. Electrical Appliances
    "Electrical Appliances": {
        "Cooling Appliances": [
            "i need ac", "where to buy fan", "cooling appliances shop",
            "air cooler", "ceiling fan",
        ],
        "Refrigerator": [
            "i need fridge", "where to buy refrigerator",
            "fridge shop", "refrigerator dealer",
        ],
        "Television": [
            "i need tv", "where to buy television", "tv shop",
            "led tv", "smart tv dealer",
        ],
        "Washing Machines": [
            "i need washing machine", "where to buy washer",
            "laundry machine shop",
        ],
        "Kitchen Appliances": [
            "i need mixer", "where to buy microwave", "kitchen appliances",
            "blender shop", "oven dealer",
        ],
    },

    # 11. Travel & Hospitality
    "Travel & Hospitality": {
        "Flight": [
            "i need flight ticket", "where to book flight", "airline booking",
        ],
        "Train": [
            "i need train ticket", "where to book train", "railway booking",
        ],
        "Bus": [
            "i need bus ticket", "where to book bus", "bus booking service",
        ],
        "Holidays": [
            "i need holiday package", "where to find tour package",
            "vacation planning", "trip booking",
        ],
        "Luxury Resorts": [
            "i need resort", "where to find luxury hotel", "5 star hotel",
            "premium resort", "resort booking",
        ],
        "Lodges": [
            "i need lodge", "where to book room", "budget hotel",
            "accommodation", "room for rent", "hotel near me",
        ],
        "Cabs": [
            "i need cab for travel", "where to book cab", "cab service",
        ],
    },

    # 12. Gifts & Jewels
    "Gifts & Jewels": {
        "Jewellery": [
            "i need jewellery", "where to buy gold", "jewellery shop near me",
            "gold shop", "silver jewellery", "diamond shop",
        ],
        "Gifts": [
            "i need gift", "where to buy gift", "gift shop near me",
            "gift items", "birthday gift", "gift store",
        ],
        "Flowers": [
            "i need flowers", "where to buy flowers", "flower shop near me",
            "flower delivery", "fresh flowers", "bouquet",
        ],
        "Toys": [
            "i need toys", "where to buy toys", "toy shop",
            "kids toys", "toy store nearby",
        ],
    },

    # 13. Sports Products
    "Sports Products": {
        "Sports": [
            "i need sports equipment", "where to buy sports gear",
            "sports shop", "cricket bat", "football",
        ],
        "Fitness": [
            "i need gym", "where to find gym", "fitness center near me",
            "yoga class", "gym membership", "fitness trainer",
        ],
        "Nutrition": [
            "i need protein", "where to buy supplements", "protein powder shop",
            "nutrition supplements",
        ],
    },

    # 14. Books & Stationery
    "Books & Stationery": {
        "Books": [
            "i need book", "where to buy book", "bookstore near me",
            "novel", "textbook shop", "book store",
        ],
        "Stationary": [
            "i need stationery", "where to buy pen", "stationery shop",
            "notebook", "school supplies", "office stationery",
        ],
    },

    # 15. Others
    "Others": {
        "Education": [
            "i need coaching", "where to find tuition", "coaching class near me",
            "training center", "academy", "class near me",
        ],
        "Fitness": [
            "i need gym", "where to find gym", "fitness center",
            "yoga studio", "workout center",
        ],
        "Pet Care": [
            "i need pet shop", "where to find vet", "pet doctor near me",
            "veterinary clinic", "pet grooming",
            ],
    },
}
# Flatten all queries
ALL_QUERIES = []
for category, subcats in QUERIES_BY_CATEGORY.items():
    for subcat, queries in subcats.items():
        ALL_QUERIES.extend(queries)

# Remove duplicates
ALL_QUERIES = list(set(ALL_QUERIES))
ALL_QUERIES.sort()

# Save
import json
import csv

# JSON
with open("user_queries_dataset.json", "w") as f:
    json.dump(ALL_QUERIES, f, indent=2)

# CSV
with open("user_queries_dataset.csv", "w") as f:
    writer = csv.writer(f)
    writer.writerow(["query"])
    for q in ALL_QUERIES:
        writer.writerow([q])

# Text file (one per line)
with open("user_queries_dataset.txt", "w") as f:
    for q in ALL_QUERIES:
        f.write(f"{q}\n")

print(f"✅ Generated {len(ALL_QUERIES)} realistic user queries")
print(f"📁 Saved to: user_queries_dataset.json/csv/txt")

# Print sample
print("\n📊 Sample queries:")
for i, q in enumerate(ALL_QUERIES[:20], 1):
    print(f"{i}. {q}")