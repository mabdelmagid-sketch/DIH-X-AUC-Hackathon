#!/usr/bin/env python3
import csv


def classify_item(row):
    item_id = row["item_id"]
    title = row["title"] if row["title"] else ""
    description = row["description"] if row["description"] else ""
    max_gap = (
        float(row["max_gap_days"])
        if row["max_gap_days"] and row["max_gap_days"] != ""
        else 999
    )
    demand_pattern = row["demand_pattern"]
    sells_every_day = row["sells_every_day"] == "1"

    title_lower = title.lower()
    desc_lower = description.lower()

    # Unknown demand pattern = low confidence
    if demand_pattern == "unknown":
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "ambient",
            "shelf_life_days": 365,
            "can_freeze": True,
            "frozen_shelf_life_days": 730,
            "perishability": "low",
            "confidence": "low",
            "notes": "Unknown demand pattern",
        }

    # Hard constraint: max_gap >= 14 means item cannot be fresh/perishable
    if max_gap >= 14:
        if "pølse" in title_lower or "hotdog" in title_lower or "burger" in title_lower:
            return {
                "item_id": item_id,
                "title": title,
                "storage_type": "refrigerated",
                "shelf_life_days": 7,
                "can_freeze": True,
                "frozen_shelf_life_days": 90,
                "perishability": "medium",
                "confidence": "medium",
                "notes": "Pre-cooked item with long gaps",
            }
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "dry",
            "shelf_life_days": 90,
            "can_freeze": True,
            "frozen_shelf_life_days": 365,
            "perishability": "low",
            "confidence": "high",
            "notes": "Long gaps - shelf-stable",
        }

    # === FOOD ITEMS FIRST ===

    # Sausages, hotdogs (MUST come before beer checks)
    if (
        "pølse" in title_lower
        or "hotdog" in title_lower
        or "frankfurter" in title_lower
        or "medister" in title_lower
        or "knæk" in title_lower
        or "ristet pølse" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 7,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "medium",
            "confidence": "high",
            "notes": "Pre-cooked sausage",
        }

    # Burgers
    if "burger" in title_lower:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 2,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "high",
            "confidence": "medium",
            "notes": "Pre-assembled burger",
        }

    # Fries
    if "pommes" in title_lower or "frites" in title_lower:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "frozen",
            "shelf_life_days": 30,
            "can_freeze": True,
            "frozen_shelf_life_days": 365,
            "perishability": "low",
            "confidence": "high",
            "notes": "Frozen fries",
        }

    # Pizzas
    if "pizza" in title_lower:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 2,
            "can_freeze": True,
            "frozen_shelf_life_days": 180,
            "perishability": "medium",
            "confidence": "medium",
            "notes": "Pre-baked pizza",
        }

    # Sushi/sashimi
    if (
        "sushi" in title_lower
        or "maki" in title_lower
        or "nigiri" in title_lower
        or "sashimi" in title_lower
        or "califonia" in title_lower
        or "alaska" in title_lower
        or "tuna" in title_lower
        or "laks" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 1,
            "can_freeze": True,
            "frozen_shelf_life_days": 30,
            "perishability": "high",
            "confidence": "high",
            "notes": "Raw fish - highly perishable",
        }

    # Salads
    if "salat" in title_lower:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 2,
            "can_freeze": False,
            "frozen_shelf_life_days": None,
            "perishability": "high",
            "confidence": "high",
            "notes": "Prepared salad",
        }

    # Soups
    if "suppe" in title_lower:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 3,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "medium",
            "confidence": "high",
            "notes": "Soup - can freeze",
        }

    # Pasta dishes
    if (
        "spaghetti" in title_lower
        or "pasta" in title_lower
        or "lasagne" in title_lower
        or "calzone" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 3,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "medium",
            "confidence": "medium",
            "notes": "Pasta dish",
        }

    # Sandwiches, wraps, pita
    if (
        "sandwich" in title_lower
        or "wrap" in title_lower
        or "pitabrød" in title_lower
        or "durum" in title_lower
        or ("pita" in title_lower and "pitabrød" not in title_lower)
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 2,
            "can_freeze": True,
            "frozen_shelf_life_days": 60,
            "perishability": "high",
            "confidence": "medium",
            "notes": "Pre-made sandwich",
        }

    # Forårsruller
    if (
        "forårsrulle" in title_lower
        or "forårsruller" in title_lower
        or "tempura" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 2,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "medium",
            "confidence": "medium",
            "notes": "Fried appetizer",
        }

    # Curry dishes
    if "karry" in title_lower or "curry" in title_lower:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 3,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "medium",
            "confidence": "medium",
            "notes": "Curry dish",
        }

    # Chicken dishes
    if "kylling" in title_lower or "chicken" in title_lower:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 2,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "high",
            "confidence": "medium",
            "notes": "Cooked chicken",
        }

    # Fish dishes
    if (
        "fisk" in title_lower
        or "fish" in title_lower
        or "filet" in title_lower
        or "torsk" in title_lower
        or "rødspætte" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 2,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "high",
            "confidence": "medium",
            "notes": "Fish dish",
        }

    # Steaks/meat dishes
    if (
        "bøf" in title_lower
        or "steak" in title_lower
        or "mørbrad" in title_lower
        or "tournedos" in title_lower
        or "schnitzel" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 2,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "high",
            "confidence": "medium",
            "notes": "Meat dish",
        }

    # Bread items
    if (
        "brød" in title_lower
        or "toast" in title_lower
        or "croissant" in title_lower
        or "bolle" in title_lower
        or "rundstykke" in title_lower
        or "wienerbrød" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "dry",
            "shelf_life_days": 5,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "low",
            "confidence": "high",
            "notes": "Bread items",
        }

    # Shots, cocktails, spirits (check before coffee)
    if (
        "shot" in title_lower
        or "whisky" in title_lower
        or "vodka" in title_lower
        or "gin" in title_lower
        or "tequila" in title_lower
        or "rum" in title_lower
        or "cognac" in title_lower
        or "irish coffee" in title_lower
        or "white russian" in title_lower
        or "bloody mary" in title_lower
        or "margarita" in title_lower
        or "daiquiri" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "ambient",
            "shelf_life_days": 730,
            "can_freeze": False,
            "frozen_shelf_life_days": None,
            "perishability": "low",
            "confidence": "high",
            "notes": "Alcoholic drink",
        }

    # Coffee drinks (ready to drink)
    if (
        "espresso" in title_lower
        or "cappuccino" in title_lower
        or "latte" in title_lower
        or "coffee" in title_lower
        or ("kaffe" in title_lower and "the" not in title_lower)
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 1,
            "can_freeze": False,
            "frozen_shelf_life_days": None,
            "perishability": "medium",
            "confidence": "medium",
            "notes": "Ready-to-drink coffee",
        }

    # Tea (check after coffee to avoid 'te' matching in coffee)
    if (
        title_lower == "te"
        or title_lower.endswith(" te")
        or " te " in title_lower
        or title_lower.startswith("te ")
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "dry",
            "shelf_life_days": 730,
            "can_freeze": True,
            "frozen_shelf_life_days": 1095,
            "perishability": "low",
            "confidence": "high",
            "notes": "Tea - shelf stable",
        }

    # Wine
    if "vin" in title_lower or "wine" in title_lower:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "ambient",
            "shelf_life_days": 365,
            "can_freeze": False,
            "frozen_shelf_life_days": None,
            "perishability": "low",
            "confidence": "high",
            "notes": "Wine",
        }

    # Beer/cider - CHECK AFTER food items
    if (
        "øl" in title_lower
        or "beer" in title_lower
        or "cider" in title_lower
        or "cider" in desc_lower
        or "grimbergen" in title_lower
        or "carlsberg" in title_lower
        or "tuborg" in title_lower
        or "guinness" in title_lower
        or "1664" in title_lower
        or "jacobsen" in title_lower
        or "kilkenny" in title_lower
        or "erdinger" in title_lower
        or "somersby" in title_lower
        or "früli" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "ambient",
            "shelf_life_days": 180,
            "can_freeze": False,
            "frozen_shelf_life_days": None,
            "perishability": "low",
            "confidence": "high",
            "notes": "Beer/cider",
        }

    # Soft drinks
    if (
        "sodavand" in title_lower
        or "cola" in title_lower
        or "fanta" in title_lower
        or "pepsi" in title_lower
        or "faxe" in title_lower
        or "tonic" in title_lower
        or "water" in title_lower
        or "vand" in title_lower
        or "mineral" in title_lower
        or "kildevand" in title_lower
        or "cocio" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "ambient",
            "shelf_life_days": 365,
            "can_freeze": False,
            "frozen_shelf_life_days": None,
            "perishability": "low",
            "confidence": "high",
            "notes": "Soft drink",
        }

    # Juice
    if (
        "juice" in title_lower
        or "saft" in title_lower
        or "appelsin" in title_lower
        or "is-te" in title_lower
        or "ice tea" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 7,
            "can_freeze": True,
            "frozen_shelf_life_days": 180,
            "perishability": "medium",
            "confidence": "high",
            "notes": "Juice",
        }

    # Chocolate, candy, baked goods
    if (
        "chokolade" in title_lower
        or "cookie" in title_lower
        or "kage" in title_lower
        or "brownie" in title_lower
        or "muffin" in title_lower
        or "tiramisu" in title_lower
        or "vaffel" in title_lower
        or "banana split" in title_lower
        or "gelato" in title_lower
        or "is" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "dry",
            "shelf_life_days": 30,
            "can_freeze": True,
            "frozen_shelf_life_days": 180,
            "perishability": "low",
            "confidence": "high",
            "notes": "Baked/sweet goods",
        }

    # Chips, snacks
    if (
        "chips" in title_lower
        or "peanuts" in title_lower
        or "snacks" in title_lower
        or "pringles" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "dry",
            "shelf_life_days": 180,
            "can_freeze": True,
            "frozen_shelf_life_days": 365,
            "perishability": "low",
            "confidence": "high",
            "notes": "Snacks",
        }

    # Dairy
    if (
        "mælk" in title_lower
        or "fløde" in title_lower
        or "ost" in title_lower
        or "cheese" in title_lower
        or "yoghurt" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 14,
            "can_freeze": True,
            "frozen_shelf_life_days": 180,
            "perishability": "high",
            "confidence": "high",
            "notes": "Dairy",
        }

    # Unspecified
    if title == "Unspecified" or title == "" or not title:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "ambient",
            "shelf_life_days": 30,
            "can_freeze": True,
            "frozen_shelf_life_days": 180,
            "perishability": "low",
            "confidence": "low",
            "notes": "Unspecified item",
        }

    # Default based on demand pattern
    if sells_every_day or demand_pattern == "daily_staple":
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 3,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "medium",
            "confidence": "medium",
            "notes": "Daily staple",
        }
    else:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "dry",
            "shelf_life_days": 30,
            "can_freeze": True,
            "frozen_shelf_life_days": 180,
            "perishability": "low",
            "confidence": "low",
            "notes": "Generic food item",
        }

    # Hard constraint: max_gap >= 14 means item cannot be fresh/perishable
    if max_gap >= 14:
        if "pølse" in title_lower or "hotdog" in title_lower or "burger" in title_lower:
            return {
                "item_id": item_id,
                "title": title,
                "storage_type": "refrigerated",
                "shelf_life_days": 7,
                "can_freeze": True,
                "frozen_shelf_life_days": 90,
                "perishability": "medium",
                "confidence": "medium",
                "notes": "Pre-cooked item with long gaps",
            }
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "dry",
            "shelf_life_days": 90,
            "can_freeze": True,
            "frozen_shelf_life_days": 365,
            "perishability": "low",
            "confidence": "high",
            "notes": "Long gaps - shelf-stable",
        }

    # === FOOD ITEMS FIRST ===

    # Sausages, hotdogs (MUST come before beer checks)
    if (
        "pølse" in title_lower
        or "hotdog" in title_lower
        or "frankfurter" in title_lower
        or "medister" in title_lower
        or "knæk" in title_lower
        or "ristet pølse" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 7,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "medium",
            "confidence": "high",
            "notes": "Pre-cooked sausage",
        }

    # Burgers
    if "burger" in title_lower:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 2,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "high",
            "confidence": "medium",
            "notes": "Pre-assembled burger",
        }

    # Fries
    if "pommes" in title_lower or "frites" in title_lower:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "frozen",
            "shelf_life_days": 30,
            "can_freeze": True,
            "frozen_shelf_life_days": 365,
            "perishability": "low",
            "confidence": "high",
            "notes": "Frozen fries",
        }

    # Pizzas
    if "pizza" in title_lower:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 2,
            "can_freeze": True,
            "frozen_shelf_life_days": 180,
            "perishability": "medium",
            "confidence": "medium",
            "notes": "Pre-baked pizza",
        }

    # Sushi/sashimi
    if (
        "sushi" in title_lower
        or "maki" in title_lower
        or "nigiri" in title_lower
        or "sashimi" in title_lower
        or "califonia" in title_lower
        or "alaska" in title_lower
        or "tuna" in title_lower
        or "laks" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 1,
            "can_freeze": True,
            "frozen_shelf_life_days": 30,
            "perishability": "high",
            "confidence": "high",
            "notes": "Raw fish - highly perishable",
        }

    # Salads
    if "salat" in title_lower:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 2,
            "can_freeze": False,
            "frozen_shelf_life_days": None,
            "perishability": "high",
            "confidence": "high",
            "notes": "Prepared salad",
        }

    # Soups
    if "suppe" in title_lower:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 3,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "medium",
            "confidence": "high",
            "notes": "Soup - can freeze",
        }

    # Pasta dishes
    if (
        "spaghetti" in title_lower
        or "pasta" in title_lower
        or "lasagne" in title_lower
        or "calzone" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 3,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "medium",
            "confidence": "medium",
            "notes": "Pasta dish",
        }

    # Sandwiches, wraps, pita
    if (
        "sandwich" in title_lower
        or "wrap" in title_lower
        or "pitabrød" in title_lower
        or "durum" in title_lower
        or "pita" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 2,
            "can_freeze": True,
            "frozen_shelf_life_days": 60,
            "perishability": "high",
            "confidence": "medium",
            "notes": "Pre-made sandwich",
        }

    # Forårsruller
    if (
        "forårsrulle" in title_lower
        or "forårsruller" in title_lower
        or "tempura" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 2,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "medium",
            "confidence": "medium",
            "notes": "Fried appetizer",
        }

    # Curry dishes
    if "karry" in title_lower or "curry" in title_lower:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 3,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "medium",
            "confidence": "medium",
            "notes": "Curry dish",
        }

    # Chicken dishes
    if "kylling" in title_lower or "chicken" in title_lower:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 2,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "high",
            "confidence": "medium",
            "notes": "Cooked chicken",
        }

    # Fish dishes
    if (
        "fisk" in title_lower
        or "fish" in title_lower
        or "filet" in title_lower
        or "torsk" in title_lower
        or "rødspætte" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 2,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "high",
            "confidence": "medium",
            "notes": "Fish dish",
        }

    # Steaks/meat dishes
    if (
        "bøf" in title_lower
        or "steak" in title_lower
        or "mørbrad" in title_lower
        or "tournedos" in title_lower
        or "schnitzel" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 2,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "high",
            "confidence": "medium",
            "notes": "Meat dish",
        }

    # Bread items
    if (
        "brød" in title_lower
        or "toast" in title_lower
        or "croissant" in title_lower
        or "bolle" in title_lower
        or "rundstykke" in title_lower
        or "wienerbrød" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "dry",
            "shelf_life_days": 5,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "low",
            "confidence": "high",
            "notes": "Bread items",
        }

    # Coffee drinks (ready to drink)
    if (
        "espresso" in title_lower
        or "cappuccino" in title_lower
        or "latte" in title_lower
        or "coffee" in title_lower
        or "kaffe" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 1,
            "can_freeze": False,
            "frozen_shelf_life_days": None,
            "perishability": "medium",
            "confidence": "medium",
            "notes": "Ready-to-drink coffee",
        }

    # Tea
    if "te" in title_lower:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "dry",
            "shelf_life_days": 730,
            "can_freeze": True,
            "frozen_shelf_life_days": 1095,
            "perishability": "low",
            "confidence": "high",
            "notes": "Tea - shelf stable",
        }

    # Shots, cocktails, spirits
    if (
        "shot" in title_lower
        or "whisky" in title_lower
        or "vodka" in title_lower
        or "gin" in title_lower
        or "tequila" in title_lower
        or "rum" in title_lower
        or "cognac" in title_lower
        or "irish coffee" in title_lower
        or "white russian" in title_lower
        or "bloody mary" in title_lower
        or "margarita" in title_lower
        or "daiquiri" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "ambient",
            "shelf_life_days": 730,
            "can_freeze": False,
            "frozen_shelf_life_days": None,
            "perishability": "low",
            "confidence": "high",
            "notes": "Alcoholic drink",
        }

    # Wine
    if "vin" in title_lower or "wine" in title_lower:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "ambient",
            "shelf_life_days": 365,
            "can_freeze": False,
            "frozen_shelf_life_days": None,
            "perishability": "low",
            "confidence": "high",
            "notes": "Wine",
        }

    # Beer/cider - CHECK AFTER food items
    if (
        "øl" in title_lower
        or "beer" in title_lower
        or "cider" in title_lower
        or "cider" in desc_lower
        or "grimbergen" in title_lower
        or "carlsberg" in title_lower
        or "tuborg" in title_lower
        or "guinness" in title_lower
        or "1664" in title_lower
        or "jacobsen" in title_lower
        or "kilkenny" in title_lower
        or "erdinger" in title_lower
        or "somersby" in title_lower
        or "früli" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "ambient",
            "shelf_life_days": 180,
            "can_freeze": False,
            "frozen_shelf_life_days": None,
            "perishability": "low",
            "confidence": "high",
            "notes": "Beer/cider",
        }

    # Soft drinks
    if (
        "sodavand" in title_lower
        or "cola" in title_lower
        or "fanta" in title_lower
        or "pepsi" in title_lower
        or "faxe" in title_lower
        or "tonic" in title_lower
        or "water" in title_lower
        or "vand" in title_lower
        or "mineral" in title_lower
        or "kildevand" in title_lower
        or "cocio" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "ambient",
            "shelf_life_days": 365,
            "can_freeze": False,
            "frozen_shelf_life_days": None,
            "perishability": "low",
            "confidence": "high",
            "notes": "Soft drink",
        }

    # Juice
    if (
        "juice" in title_lower
        or "saft" in title_lower
        or "appelsin" in title_lower
        or "is-te" in title_lower
        or "ice tea" in title_lower
        or "te" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 7,
            "can_freeze": True,
            "frozen_shelf_life_days": 180,
            "perishability": "medium",
            "confidence": "high",
            "notes": "Juice",
        }

    # Chocolate, candy, baked goods
    if (
        "chokolade" in title_lower
        or "cookie" in title_lower
        or "kage" in title_lower
        or "brownie" in title_lower
        or "muffin" in title_lower
        or "tiramisu" in title_lower
        or "vaffel" in title_lower
        or "banana split" in title_lower
        or "gelato" in title_lower
        or "is" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "dry",
            "shelf_life_days": 30,
            "can_freeze": True,
            "frozen_shelf_life_days": 180,
            "perishability": "low",
            "confidence": "high",
            "notes": "Baked/sweet goods",
        }

    # Chips, snacks
    if (
        "chips" in title_lower
        or "peanuts" in title_lower
        or "snacks" in title_lower
        or "pringles" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "dry",
            "shelf_life_days": 180,
            "can_freeze": True,
            "frozen_shelf_life_days": 365,
            "perishability": "low",
            "confidence": "high",
            "notes": "Snacks",
        }

    # Dairy
    if (
        "mælk" in title_lower
        or "fløde" in title_lower
        or "ost" in title_lower
        or "cheese" in title_lower
        or "yoghurt" in title_lower
        or " Crem" in title_lower
    ):
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 14,
            "can_freeze": True,
            "frozen_shelf_life_days": 180,
            "perishability": "high",
            "confidence": "high",
            "notes": "Dairy",
        }

    # Unspecified
    if title == "Unspecified" or title == "" or not title:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "ambient",
            "shelf_life_days": 30,
            "can_freeze": True,
            "frozen_shelf_life_days": 180,
            "perishability": "low",
            "confidence": "low",
            "notes": "Unspecified item",
        }

    # Default based on demand pattern
    if sells_every_day or demand_pattern == "daily_staple":
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "refrigerated",
            "shelf_life_days": 3,
            "can_freeze": True,
            "frozen_shelf_life_days": 90,
            "perishability": "medium",
            "confidence": "medium",
            "notes": "Daily staple",
        }
    else:
        return {
            "item_id": item_id,
            "title": title,
            "storage_type": "dry",
            "shelf_life_days": 30,
            "can_freeze": True,
            "frozen_shelf_life_days": 180,
            "perishability": "low",
            "confidence": "low",
            "notes": "Generic food item",
        }


# Read source data
with open(
    "/home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting/data/demo/items_to_enrich.csv",
    "r",
    encoding="utf-8",
) as f:
    reader = csv.DictReader(f)
    all_rows = list(reader)

# Take rows from index 3048 to 3048+761 (0-indexed, so 3048 to 3809)
source_rows = all_rows[3048:3810]

print(f"Processing {len(source_rows)} rows")

# Process each row
results = []
for row in source_rows:
    result = classify_item(row)
    results.append(result)

# Write output
output_path = "/home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting/data/demo/shelf_life_part_05.csv"
with open(output_path, "w", newline="", encoding="utf-8") as f:
    fieldnames = [
        "item_id",
        "title",
        "storage_type",
        "shelf_life_days",
        "can_freeze",
        "frozen_shelf_life_days",
        "perishability",
        "confidence",
        "notes",
    ]
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(results)

print(f"Wrote {len(results)} rows to {output_path}")
