#!/usr/bin/env python3
"""
Seed ingredients and link them to products via recipes.
Run AFTER seed-demo.py.
"""
import requests
import json
import uuid
import random

# === CONFIG ===
import os
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ucqqeuogbhyqmsabqyac.supabase.co")
SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]  # Set via env var
ORG_ID = "9a06b980-f639-47da-a88d-9ad14a5b687b"
LOC_ID = "7605faca-4a9c-4def-a984-bd9040d325c2"

def uid():
    return str(uuid.uuid4())

def api(method, table, data=None, params=None):
    headers = {
        "apikey": SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    try:
        resp = getattr(requests, method.lower())(url, headers=headers, json=data, timeout=15)
        if resp.status_code >= 400:
            print(f"    ERROR {resp.status_code}: {resp.text[:200]}")
            return None
        return resp.json() if resp.text else None
    except Exception as e:
        print(f"    Exception: {e}")
        return None

# Get existing products
print("Fetching existing products...")
products = api("GET", "products", params={
    "organization_id": f"eq.{ORG_ID}",
    "select": "id,name,category_id",
})
if not products:
    print("No products found! Run seed-demo.py first.")
    exit(1)

product_map = {p["name"]: p["id"] for p in products}
print(f"  Found {len(product_map)} products")

# === INGREDIENTS ===
print("\n1. Creating ingredients...")
ingredients_data = [
    # (name, category_enum, unit, cost_cents_per_unit, stock_qty, min_stock, storage)
    # Dairy & Eggs
    ("Whole Milk", "DAIRY", "ml", 30, 5000, 2000, "Refrigerate at 4C"),
    ("Oat Milk", "DAIRY", "ml", 50, 3000, 1000, "Refrigerate after opening"),
    ("Heavy Cream", "DAIRY", "ml", 60, 2000, 800, "Refrigerate at 4C"),
    ("Butter", "DAIRY", "g", 120, 2000, 500, "Refrigerate"),
    ("Eggs (Large)", "DAIRY", "piece", 40, 200, 50, "Refrigerate"),
    ("Greek Yoghurt", "DAIRY", "g", 80, 3000, 1000, "Refrigerate"),
    ("Cream Cheese", "DAIRY", "g", 100, 1500, 500, "Refrigerate"),
    # Produce
    ("Avocado", "PRODUCE", "piece", 250, 50, 15, "Store at room temp"),
    ("Tomatoes", "PRODUCE", "g", 40, 3000, 800, "Refrigerate"),
    ("Spinach", "PRODUCE", "g", 60, 1500, 400, "Refrigerate"),
    ("Lettuce (Romaine)", "PRODUCE", "g", 30, 2000, 500, "Refrigerate"),
    ("Cucumber", "PRODUCE", "piece", 120, 30, 10, "Refrigerate"),
    ("Red Onion", "PRODUCE", "piece", 80, 40, 10, "Cool dry place"),
    ("Lemon", "PRODUCE", "piece", 60, 50, 15, "Room temp"),
    ("Fresh Berries Mix", "PRODUCE", "g", 200, 2000, 500, "Refrigerate"),
    ("Banana", "PRODUCE", "piece", 40, 60, 20, "Room temp"),
    ("Orange", "PRODUCE", "piece", 80, 80, 25, "Room temp"),
    ("Garlic", "PRODUCE", "piece", 30, 30, 10, "Cool dry place"),
    # Proteins
    ("Smoked Salmon", "SEAFOOD", "g", 450, 1000, 300, "Refrigerate at 2C"),
    ("Turkey Breast", "MEAT", "g", 320, 2000, 500, "Refrigerate"),
    ("Chicken Breast", "MEAT", "g", 200, 3000, 800, "Refrigerate at 2C"),
    ("Falafel Mix", "DRY_GOODS", "g", 150, 2000, 600, "Room temp dry"),
    ("Canadian Bacon", "MEAT", "g", 380, 1000, 300, "Refrigerate"),
    # Bakery
    ("Sourdough Loaf", "GRAINS", "piece", 350, 20, 8, "Room temp, use within 3 days"),
    ("Croissant Dough", "BAKING", "g", 180, 3000, 1000, "Freeze at -18C"),
    ("Bagels", "GRAINS", "piece", 120, 40, 12, "Room temp, use within 2 days"),
    ("Pita Bread", "GRAINS", "piece", 80, 40, 12, "Room temp"),
    ("Tortilla Wraps", "GRAINS", "piece", 60, 50, 15, "Room temp"),
    # Pantry
    ("Espresso Coffee Beans", "BEVERAGES", "g", 250, 5000, 1500, "Cool dry place, sealed"),
    ("Green Tea Leaves", "BEVERAGES", "g", 300, 1000, 300, "Cool dry place"),
    ("Chai Spice Blend", "SPICES", "g", 400, 500, 150, "Cool dry place"),
    ("Cocoa Powder", "BAKING", "g", 200, 1000, 300, "Cool dry place"),
    ("Quinoa", "GRAINS", "g", 120, 3000, 800, "Cool dry place"),
    ("Granola", "GRAINS", "g", 100, 3000, 800, "Cool dry place"),
    ("Olive Oil", "OILS", "ml", 150, 2000, 500, "Room temp"),
    ("Honey", "SAUCES", "ml", 200, 1000, 300, "Room temp"),
    ("Mixed Nuts", "DRY_GOODS", "g", 250, 2000, 600, "Cool dry place"),
    ("Chocolate Chips", "BAKING", "g", 180, 2000, 500, "Cool dry place"),
    ("Hummus", "SAUCES", "g", 120, 2000, 600, "Refrigerate"),
    # Sauces
    ("Hollandaise Sauce", "SAUCES", "ml", 200, 1000, 300, "Refrigerate"),
    ("Caesar Dressing", "SAUCES", "ml", 150, 1000, 300, "Refrigerate"),
    ("Thai Peanut Sauce", "SAUCES", "ml", 180, 800, 250, "Refrigerate"),
    ("Feta Cheese", "DAIRY", "g", 200, 1500, 500, "Refrigerate"),
    ("Parmesan", "DAIRY", "g", 300, 1000, 300, "Refrigerate"),
    ("Cheddar", "DAIRY", "g", 180, 2000, 500, "Refrigerate"),
    ("Mozzarella", "DAIRY", "g", 200, 1500, 500, "Refrigerate"),
]

ingredient_ids = {}
for name, category, unit, cost, stock, min_stock, storage in ingredients_data:
    iid = uid()
    result = api("POST", "ingredients", {
        "id": iid,
        "organization_id": ORG_ID,
        "name": name,
        "category": category,
        "unit": unit,
        "cost_per_unit": cost,
        "min_stock_level": min_stock,
        "storage_instructions": storage,
        "is_active": True,
    })
    if result:
        iid = result[0]["id"] if isinstance(result, list) else result["id"]
    ingredient_ids[name] = iid

print(f"  Created {len(ingredient_ids)} ingredients")

# === INGREDIENT STOCK ===
print("\n2. Creating ingredient stock levels...")
stock_count = 0
for name, category, unit, cost, stock, min_stock, storage in ingredients_data:
    iid = ingredient_ids.get(name)
    if not iid:
        continue
    result = api("POST", "ingredient_stock", {
        "id": uid(),
        "ingredient_id": iid,
        "location_id": LOC_ID,
        "quantity": stock + random.randint(-200, 500),
    })
    if result:
        stock_count += 1
print(f"  Created {stock_count} stock records")

# === RECIPES (linking products to ingredients) ===
print("\n3. Creating recipes and linking to products...")
# Map product names to their ingredient recipes
recipe_definitions = {
    "Flat White": [
        ("Espresso Coffee Beans", 18, "g"),
        ("Whole Milk", 150, "ml"),
    ],
    "Cappuccino": [
        ("Espresso Coffee Beans", 18, "g"),
        ("Whole Milk", 120, "ml"),
    ],
    "Americano": [
        ("Espresso Coffee Beans", 18, "g"),
    ],
    "Chai Latte": [
        ("Chai Spice Blend", 8, "g"),
        ("Whole Milk", 200, "ml"),
        ("Honey", 10, "ml"),
    ],
    "Green Tea": [
        ("Green Tea Leaves", 5, "g"),
        ("Honey", 5, "ml"),
    ],
    "Hot Chocolate": [
        ("Cocoa Powder", 25, "g"),
        ("Whole Milk", 200, "ml"),
        ("Heavy Cream", 30, "ml"),
        ("Chocolate Chips", 10, "g"),
    ],
    "Fresh Orange Juice": [
        ("Orange", 3, "piece"),
    ],
    "Green Smoothie": [
        ("Spinach", 60, "g"),
        ("Banana", 1, "piece"),
        ("Oat Milk", 200, "ml"),
        ("Honey", 10, "ml"),
    ],
    "Iced Latte": [
        ("Espresso Coffee Beans", 18, "g"),
        ("Whole Milk", 180, "ml"),
    ],
    "Berry Blast Smoothie": [
        ("Fresh Berries Mix", 150, "g"),
        ("Banana", 1, "piece"),
        ("Greek Yoghurt", 100, "g"),
        ("Honey", 15, "ml"),
    ],
    "Avocado & Egg Sandwich": [
        ("Sourdough Loaf", 1, "piece"),
        ("Avocado", 1, "piece"),
        ("Eggs (Large)", 2, "piece"),
        ("Tomatoes", 40, "g"),
        ("Lemon", 0.5, "piece"),
    ],
    "Smoked Salmon Bagel": [
        ("Bagels", 1, "piece"),
        ("Smoked Salmon", 80, "g"),
        ("Cream Cheese", 30, "g"),
        ("Red Onion", 0.25, "piece"),
        ("Lemon", 0.25, "piece"),
    ],
    "Turkey Club Wrap": [
        ("Tortilla Wraps", 1, "piece"),
        ("Turkey Breast", 100, "g"),
        ("Lettuce (Romaine)", 30, "g"),
        ("Tomatoes", 40, "g"),
        ("Cheddar", 25, "g"),
    ],
    "Falafel Pita": [
        ("Pita Bread", 1, "piece"),
        ("Falafel Mix", 120, "g"),
        ("Hummus", 40, "g"),
        ("Lettuce (Romaine)", 20, "g"),
        ("Tomatoes", 30, "g"),
    ],
    "Grilled Cheese": [
        ("Sourdough Loaf", 1, "piece"),
        ("Cheddar", 60, "g"),
        ("Mozzarella", 40, "g"),
        ("Butter", 15, "g"),
    ],
    "Caesar Salad": [
        ("Lettuce (Romaine)", 120, "g"),
        ("Parmesan", 25, "g"),
        ("Caesar Dressing", 40, "ml"),
        ("Chicken Breast", 100, "g"),
        ("Sourdough Loaf", 0.5, "piece"),
    ],
    "Greek Salad": [
        ("Tomatoes", 80, "g"),
        ("Cucumber", 1, "piece"),
        ("Red Onion", 0.5, "piece"),
        ("Feta Cheese", 60, "g"),
        ("Olive Oil", 15, "ml"),
    ],
    "Quinoa Bowl": [
        ("Quinoa", 80, "g"),
        ("Avocado", 0.5, "piece"),
        ("Spinach", 40, "g"),
        ("Tomatoes", 40, "g"),
        ("Lemon", 0.5, "piece"),
        ("Olive Oil", 10, "ml"),
    ],
    "Thai Chicken Salad": [
        ("Chicken Breast", 120, "g"),
        ("Lettuce (Romaine)", 80, "g"),
        ("Thai Peanut Sauce", 40, "ml"),
        ("Mixed Nuts", 20, "g"),
        ("Lemon", 0.5, "piece"),
    ],
    "Butter Croissant": [
        ("Croissant Dough", 80, "g"),
        ("Butter", 20, "g"),
    ],
    "Pain au Chocolat": [
        ("Croissant Dough", 80, "g"),
        ("Chocolate Chips", 30, "g"),
    ],
    "Cinnamon Roll": [
        ("Croissant Dough", 100, "g"),
        ("Butter", 15, "g"),
        ("Honey", 20, "ml"),
    ],
    "Almond Croissant": [
        ("Croissant Dough", 80, "g"),
        ("Mixed Nuts", 30, "g"),
        ("Butter", 10, "g"),
    ],
    "Eggs Benedict": [
        ("Sourdough Loaf", 1, "piece"),
        ("Eggs (Large)", 2, "piece"),
        ("Canadian Bacon", 60, "g"),
        ("Hollandaise Sauce", 40, "ml"),
        ("Spinach", 20, "g"),
    ],
    "Acai Bowl": [
        ("Fresh Berries Mix", 120, "g"),
        ("Banana", 1, "piece"),
        ("Granola", 40, "g"),
        ("Honey", 10, "ml"),
    ],
    "Granola & Yoghurt": [
        ("Granola", 80, "g"),
        ("Greek Yoghurt", 150, "g"),
        ("Fresh Berries Mix", 40, "g"),
        ("Honey", 10, "ml"),
    ],
    "Full Danish Breakfast": [
        ("Eggs (Large)", 3, "piece"),
        ("Canadian Bacon", 80, "g"),
        ("Sourdough Loaf", 1, "piece"),
        ("Butter", 20, "g"),
        ("Tomatoes", 60, "g"),
    ],
    "Hummus & Crackers": [
        ("Hummus", 80, "g"),
        ("Olive Oil", 5, "ml"),
    ],
    "Carrot Cake Slice": [
        ("Cream Cheese", 40, "g"),
        ("Butter", 15, "g"),
        ("Eggs (Large)", 1, "piece"),
        ("Honey", 15, "ml"),
    ],
    "Chocolate Brownie": [
        ("Chocolate Chips", 60, "g"),
        ("Butter", 40, "g"),
        ("Eggs (Large)", 2, "piece"),
        ("Cocoa Powder", 20, "g"),
    ],
    "Fruit Tart": [
        ("Butter", 30, "g"),
        ("Fresh Berries Mix", 80, "g"),
        ("Heavy Cream", 50, "ml"),
        ("Eggs (Large)", 1, "piece"),
    ],
}

recipe_count = 0
for product_name, ingredients in recipe_definitions.items():
    product_id = product_map.get(product_name)
    if not product_id:
        print(f"  Skipping {product_name} - product not found")
        continue

    # Create recipe
    recipe_id = uid()
    recipe = api("POST", "recipes", {
        "id": recipe_id,
        "organization_id": ORG_ID,
        "name": f"{product_name} Recipe",
        "product_id": product_id,
        "yield_quantity": 1,
        "yield_unit": "serving",
        "is_active": True,
        "category": "Standard",
    })
    if not recipe:
        print(f"  Failed to create recipe for {product_name}")
        continue

    recipe_id = recipe[0]["id"] if isinstance(recipe, list) else recipe["id"]

    # Link ingredients
    for idx, (ing_name, qty, unit) in enumerate(ingredients):
        ing_id = ingredient_ids.get(ing_name)
        if not ing_id:
            print(f"    Ingredient not found: {ing_name}")
            continue
        api("POST", "recipe_ingredients", {
            "id": uid(),
            "recipe_id": recipe_id,
            "ingredient_id": ing_id,
            "quantity": qty,
            "unit": unit,
            "sort_order": idx,
        })

    recipe_count += 1

print(f"  Created {recipe_count} recipes with ingredient links")

print("\n=== INGREDIENT SEEDING COMPLETE ===")
print(f"  Ingredients: {len(ingredient_ids)}")
print(f"  Stock records: {stock_count}")
print(f"  Recipes (product links): {recipe_count}")
