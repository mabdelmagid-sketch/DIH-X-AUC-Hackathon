#!/usr/bin/env python3
"""
Classify production items with shelf life using:
1. Rule-based Danish food keyword matching (high confidence)
2. Claude Haiku for remaining unknowns (medium confidence)

Output: data/raw/production_shelf_life.csv
"""

import csv
import os
import json
import time

INPUT = "data/raw/production_items_to_enrich.csv"
OUTPUT = "data/raw/production_shelf_life.csv"


def classify_item_rules(title, max_gap_days):
    """Rule-based classifier using Danish food keywords. Returns dict or None if no match."""
    max_gap = float(max_gap_days) if max_gap_days and str(max_gap_days) != "nan" else 0
    title_lower = (title or "").lower()
    is_not_fresh = max_gap >= 14

    # Beverages - alcohol
    if any(w in title_lower for w in [
        "øl", "fadøl", "flaske", "cider", "vin", "shots", "drinks", "beverage",
        "rødvin", "hvidvin", "rosé", "champagne", "prosecco", "bobler", "cremant",
        "gin", "tonic", "rum", "vodka", "whisky", "cognac", "likør", "aperol",
        "spritz", "cocktail", "mojito", "sangria", "gløgg",
    ]):
        return dict(storage_type="ambient", shelf_life_days=365, can_freeze=False,
                    perishability="low", confidence="high", notes="alcoholic beverages")

    # Hot drinks
    if any(w in title_lower for w in [
        "kaffe", "espresso", "cappuccino", "latte", "americano", "te", "chai",
        "cortado", "flat white", "mocha", "chokolade", "kakao", "iskaffe",
    ]):
        return dict(storage_type="dry", shelf_life_days=365, can_freeze=False,
                    perishability="low", confidence="high", notes="coffee/tea/hot drinks")

    # Soft drinks
    if any(w in title_lower for w in [
        "sodavand", "cola", "pepsi", "cocio", "juice", "saft",
        "fanta", "sprite", "danskvand", "kildevand", "vand", "smoothie",
        "limonade", "iste", "energy", "redbull", "monster",
    ]):
        # "vand" alone might match "vandmelon" etc - be careful
        if title_lower.strip() in ["vand", "danskvand", "kildevand"] or \
           any(w in title_lower for w in ["sodavand", "cola", "pepsi", "fanta", "sprite"]):
            return dict(storage_type="ambient", shelf_life_days=365, can_freeze=False,
                        perishability="low", confidence="high", notes="soft drinks")
        if any(w in title_lower for w in ["juice", "smoothie"]):
            return dict(storage_type="refrigerated", shelf_life_days=7, can_freeze=True,
                        perishability="medium", confidence="high", notes="fresh juice/smoothie")

    # Pizza
    if "pizza" in title_lower:
        if is_not_fresh:
            return dict(storage_type="frozen", shelf_life_days=90, can_freeze=True,
                        perishability="medium", confidence="high", notes="pizza (frozen/long shelf)")
        return dict(storage_type="refrigerated", shelf_life_days=2, can_freeze=True,
                    perishability="high", confidence="high", notes="fresh pizza")

    # Kebab/wraps
    if any(w in title_lower for w in ["kebab", "durum", "pita", "wrap", "falafel", "shawarma"]):
        if is_not_fresh:
            return dict(storage_type="frozen", shelf_life_days=60, can_freeze=True,
                        perishability="medium", confidence="high", notes="wraps/kebab frozen")
        return dict(storage_type="refrigerated", shelf_life_days=1, can_freeze=True,
                    perishability="high", confidence="high", notes="wraps/kebab fresh")

    # Burgers/sandwiches
    if any(w in title_lower for w in ["burger", "sandwich", "toast", "panini", "ciabatta"]):
        if is_not_fresh:
            return dict(storage_type="frozen", shelf_life_days=60, can_freeze=True,
                        perishability="medium", confidence="high", notes="sandwiches frozen")
        return dict(storage_type="refrigerated", shelf_life_days=1, can_freeze=True,
                    perishability="high", confidence="high", notes="sandwiches fresh")

    # Hotdogs
    if any(w in title_lower for w in ["pølse", "hotdog", "hot dog", "frankfurter", "medister", "ristet"]):
        if is_not_fresh:
            return dict(storage_type="frozen", shelf_life_days=60, can_freeze=True,
                        perishability="medium", confidence="high", notes="processed meat frozen")
        return dict(storage_type="refrigerated", shelf_life_days=3, can_freeze=True,
                    perishability="medium", confidence="high", notes="processed meat")

    # Meat
    if any(w in title_lower for w in [
        "kylling", "chicken", "kød", "bøf", "steak", "flæsk", "schnitzel",
        "kotelet", "spareribs", "okse", "svin", "lam", "and", "grill",
        "ribben", "pulled", "bacon", "hereford", "wagyu",
    ]):
        if is_not_fresh:
            return dict(storage_type="frozen", shelf_life_days=90, can_freeze=True,
                        perishability="medium", confidence="high", notes="meat frozen")
        return dict(storage_type="refrigerated", shelf_life_days=2, can_freeze=True,
                    perishability="high", confidence="high", notes="meat fresh")

    # Seafood
    if any(w in title_lower for w in [
        "fisk", "fiskefilet", "laks", "tun", "rejer", "skaldyr", "sild",
        "torsk", "rødspætte", "fish", "salmon", "shrimp", "calamari",
    ]):
        if is_not_fresh:
            return dict(storage_type="frozen", shelf_life_days=60, can_freeze=True,
                        perishability="medium", confidence="high", notes="seafood frozen")
        return dict(storage_type="refrigerated", shelf_life_days=1, can_freeze=True,
                    perishability="high", confidence="high", notes="seafood fresh")

    # Frozen fried items
    if any(w in title_lower for w in [
        "pommes", "fritter", "fries", "nuggets", "løgring", "spring roll",
        "forårsrulle", "mozzarella stick",
    ]):
        return dict(storage_type="frozen", shelf_life_days=90, can_freeze=True,
                    perishability="low", confidence="high", notes="frozen fried items")

    # Pastries/cakes
    if any(w in title_lower for w in [
        "kage", "tærte", "brownie", "macaron", "trøffel", "flødekage",
        "cheesecake", "muffin", "croissant", "wienerbrød", "kanelsneg",
        "lagkage", "dessert", "pandekage", "crème", "tiramisu",
    ]):
        if is_not_fresh:
            return dict(storage_type="dry", shelf_life_days=30, can_freeze=False,
                        perishability="low", confidence="medium", notes="pastries shelf-stable")
        return dict(storage_type="refrigerated", shelf_life_days=3, can_freeze=True,
                    perishability="medium", confidence="medium", notes="pastries fresh")

    # Bread
    if any(w in title_lower for w in [
        "brød", "bolle", "rugbrød", "surdej", "flute", "baguette",
        "focaccia", "pitabrød", "naan",
    ]):
        if is_not_fresh:
            return dict(storage_type="dry", shelf_life_days=7, can_freeze=True,
                        perishability="low", confidence="high", notes="bread products")
        return dict(storage_type="refrigerated", shelf_life_days=3, can_freeze=True,
                    perishability="medium", confidence="high", notes="bread fresh")

    # Salads
    if any(w in title_lower for w in ["salat", "grøntsag", "tomat", "agurk", "grøn"]):
        return dict(storage_type="refrigerated", shelf_life_days=3, can_freeze=False,
                    perishability="high", confidence="high", notes="fresh salads/vegetables")

    # Pasta/rice
    if any(w in title_lower for w in [
        "pasta", "spaghetti", "penne", "gnocchi", "tortellini", "ravioli",
        "lasagne", "carbonara", "bolognese", "ris", "risotto", "nudel",
    ]):
        if is_not_fresh:
            return dict(storage_type="frozen", shelf_life_days=60, can_freeze=True,
                        perishability="medium", confidence="medium", notes="pasta/rice frozen")
        return dict(storage_type="refrigerated", shelf_life_days=2, can_freeze=True,
                    perishability="medium", confidence="medium", notes="pasta/rice fresh")

    # Sauces/dressings
    if any(w in title_lower for w in [
        "sauce", "dressing", "mayo", "remoulade", "ketchup", "sennep",
        "aioli", "pesto", "dip",
    ]):
        return dict(storage_type="refrigerated", shelf_life_days=14, can_freeze=False,
                    perishability="medium", confidence="high", notes="sauces/condiments")

    # Cheese
    if any(w in title_lower for w in ["ost", "cheese", "mozzarella", "cheddar", "brie", "parmesan"]):
        return dict(storage_type="refrigerated", shelf_life_days=14, can_freeze=True,
                    perishability="medium", confidence="high", notes="cheese")

    # Ice cream
    if any(w in title_lower for w in ["is", "gelato", "sorbet", "sundae", "milkshake"]):
        # "is" alone is too short - might match other words
        if title_lower.strip() == "is" or any(w in title_lower for w in ["gelato", "sorbet", "sundae", "softice", "kugleis"]):
            return dict(storage_type="frozen", shelf_life_days=180, can_freeze=True,
                        perishability="low", confidence="high", notes="frozen desserts")

    # Smørrebrød/open sandwiches
    if any(w in title_lower for w in ["smørrebrød", "åbent"]):
        return dict(storage_type="refrigerated", shelf_life_days=1, can_freeze=False,
                    perishability="high", confidence="high", notes="open sandwiches")

    # Buffet/ready meals
    if any(w in title_lower for w in ["buffet", "aften", "frokost", "menu", "tallerken", "ret"]):
        return dict(storage_type="refrigerated", shelf_life_days=1, can_freeze=False,
                    perishability="high", confidence="medium", notes="ready-to-eat meals")

    # Chips/snacks
    if any(w in title_lower for w in ["chips", "snack", "nødder", "popcorn", "pose"]):
        return dict(storage_type="ambient", shelf_life_days=180, can_freeze=False,
                    perishability="low", confidence="high", notes="shelf-stable snacks")

    # Candy/confectionery
    if any(w in title_lower for w in [
        "slik", "chokolade bar", "lakrids", "bolsje", "tyggegummi", "daim",
        "snickers", "mars", "twix", "kitkat",
    ]):
        return dict(storage_type="ambient", shelf_life_days=365, can_freeze=False,
                    perishability="low", confidence="high", notes="confectionery")

    # Eggs/dairy
    if any(w in title_lower for w in ["æg", "mælk", "yoghurt", "fløde", "smør"]):
        return dict(storage_type="refrigerated", shelf_life_days=7, can_freeze=False,
                    perishability="medium", confidence="high", notes="dairy/eggs")

    # Soup
    if any(w in title_lower for w in ["suppe", "soup"]):
        if is_not_fresh:
            return dict(storage_type="frozen", shelf_life_days=90, can_freeze=True,
                        perishability="low", confidence="medium", notes="soup frozen")
        return dict(storage_type="refrigerated", shelf_life_days=2, can_freeze=True,
                    perishability="medium", confidence="medium", notes="soup fresh")

    return None  # No rule matched


def classify_fallback(title, max_gap_days):
    """Fallback for items that don't match any rule."""
    max_gap = float(max_gap_days) if max_gap_days and str(max_gap_days) != "nan" else 0
    if max_gap >= 14:
        return dict(storage_type="ambient", shelf_life_days=30, can_freeze=False,
                    perishability="low", confidence="low", notes="assumed shelf-stable (no rule match)")
    return dict(storage_type="refrigerated", shelf_life_days=2, can_freeze=True,
                perishability="medium", confidence="low", notes="assumed perishable (no rule match)")


def main():
    import pandas as pd

    df = pd.read_csv(INPUT)
    print(f"Loaded {len(df)} items")

    results = []
    rule_matched = 0
    fallback_count = 0

    for _, row in df.iterrows():
        item_id = row["item_id"]
        title = str(row["title"]) if pd.notna(row["title"]) else ""
        max_gap = row["max_gap_days"] if pd.notna(row["max_gap_days"]) else 0
        avg_gap = row["avg_gap_days"] if pd.notna(row["avg_gap_days"]) else 1.0

        result = classify_item_rules(title, max_gap)
        if result is not None:
            rule_matched += 1
        else:
            result = classify_fallback(title, max_gap)
            fallback_count += 1

        results.append({
            "item_id": item_id,
            "title": title,
            "avg_gap_days": round(avg_gap, 2),
            **result,
        })

    out_df = pd.DataFrame(results)
    out_df.to_csv(OUTPUT, index=False)

    print(f"\nClassification complete:")
    print(f"  Rule-based: {rule_matched} ({rule_matched/len(df)*100:.1f}%)")
    print(f"  Fallback:   {fallback_count} ({fallback_count/len(df)*100:.1f}%)")
    print(f"\nConfidence distribution:")
    print(out_df["confidence"].value_counts().to_string())
    print(f"\nPerishability distribution:")
    print(out_df["perishability"].value_counts().to_string())
    print(f"\nShelf life stats:")
    print(f"  Mean:   {out_df['shelf_life_days'].mean():.0f} days")
    print(f"  Median: {out_df['shelf_life_days'].median():.0f} days")
    print(f"  <3d:    {(out_df['shelf_life_days'] <= 3).sum()} items")
    print(f"  3-14d:  {((out_df['shelf_life_days'] > 3) & (out_df['shelf_life_days'] <= 14)).sum()} items")
    print(f"  14-90d: {((out_df['shelf_life_days'] > 14) & (out_df['shelf_life_days'] <= 90)).sum()} items")
    print(f"  >90d:   {(out_df['shelf_life_days'] > 90).sum()} items")
    print(f"\nSaved to {OUTPUT}")

    # Show items that need Haiku (low confidence)
    low_conf = out_df[out_df["confidence"] == "low"]
    print(f"\n{len(low_conf)} items with low confidence (candidates for Haiku):")
    print(low_conf[["item_id", "title", "shelf_life_days", "notes"]].head(20).to_string())


if __name__ == "__main__":
    main()
