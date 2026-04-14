#!/usr/bin/env python3
"""
Danish Food/Product Classifier
Classifies items based on Danish titles and max_gap_days (shelf life indicators)
"""

import pandas as pd
import re
from pathlib import Path

# File paths
INPUT_FILE = Path("/home/yahyahammoudeh/Documents/loving loyalty internship/data/raw/haiku_mega_6.csv")
OUTPUT_FILE = Path("/home/yahyahammoudeh/Documents/loving loyalty internship/data/raw/haiku_result_6.csv")

# Classification rules
NON_FOOD_KEYWORDS = {
    'klip', 'haircut', 'massage', 'repair', 'reparation', 'entré', 'gavekort',
    'giftcard', 'clothing', 'tøj', 'røg', 'rabatkort', 'discount', 'activity',
    'aktivitet', 'pant', 'bottle deposit', 'spillekort', 'kort', 'card',
    'afgang', 'service', 'betaling', 'hævning', 'penge', 'oplevelse',
    'experience', 'billetter', 'tickets', 'entrebillet'
}

FRESH_PERISHABLE_KEYWORDS = {
    'sandwich', 'sushi', 'salat', 'bowl', 'rå', 'frisk', 'raw',
    'yogurt', 'youghurt', 'fresh'
}

SHORT_SHELF_KEYWORDS = {
    'brød', 'bread', 'bagel', 'croissant', 'wienerbrød', 'kager', 'cake',
    'pastry', 'cooked', 'kogt', 'mad', 'meal', 'ost', 'cheese', 'smør',
    'butter', 'mælk', 'milk', 'yoghurt', 'pizza', 'pizza'
}

ALCOHOL_KEYWORDS = {
    'beer', 'øl', 'vine', 'wine', 'spiritus', 'snaps', 'whiskey', 'vodka',
    'rom', 'rum', 'cognac', 'liqueur', 'likør', 'champagne', 'prosecco',
    'bailey', 'jäger', 'underberg', 'tuborg', 'carlsberg', 'faxe', 'crabbies',
    'breezer', 'fernet', 'jd', 'tallisker', 'cider'
}

MEDIUM_SHELF_KEYWORDS = {
    'sauce', 'dressing', 'konserves', 'canned', 'dåse', 'frozen', 'frosset',
    'pølse', 'sausage', 'bacon', 'skinke', 'ham', 'pate', 'leverpostej',
    'marmelade', 'jam', 'olie', 'oil', 'eddike', 'vinegar'
}

LONG_SHELF_KEYWORDS = {
    'saft', 'juice', 'drikke', 'drink', 'vand', 'water', 'cola', 'sodavand',
    'soda', 'kaffe', 'coffee', 'te', 'tea', 'kakao', 'chokolade', 'chocolate',
    'candy', 'slik', 'bonbon', 'chips', 'snack', 'kiks', 'cookies',
    'tørt', 'dry', 'pulver', 'powder', 'fløde', 'cream', 'konserves',
    'rod bull', 'red bull', 'energidrik', 'energy', 'isotonic', 'ayran',
    'gazoz', 'kondi', 'marinello', 'merino'
}

def classify_item(item_id, title, max_gap_days):
    """
    Classify a single item based on its Danish title and max_gap_days.

    Returns: (shelf_life_days, perishability, confidence, storage_type, notes)
    """

    # Handle "Unspecified" title
    if pd.isna(title) or str(title).strip().lower() == "unspecified":
        return (14, "medium_shelf", 0.7, "Room Temperature", "Unspecified product - default to medium shelf")

    title_lower = str(title).lower().strip()

    # Rule 1: max_gap >= 14 means NOT fresh
    is_not_fresh = max_gap_days >= 14

    # Rule 2: Check for non-food services
    if any(keyword in title_lower for keyword in NON_FOOD_KEYWORDS):
        # Special handling for some non-foods
        if 'card' in title_lower or 'kort' in title_lower or 'spillekort' in title_lower:
            return (9999, "non_food", 0.95, "Not Applicable", f"Service/Card product - {title}")
        if any(k in title_lower for k in ['reparation', 'repair', 'service', 'entré']):
            return (9999, "non_food", 0.95, "Not Applicable", f"Service - {title}")
        if any(k in title_lower for k in ['tøj', 'clothing', 'cardigan', 'merino']):
            return (9999, "non_food", 0.90, "Not Applicable", f"Clothing - {title}")
        if any(k in title_lower for k in ['hævning', 'penge', 'betaling']):
            return (9999, "non_food", 0.95, "Not Applicable", f"Financial service - {title}")
        # Generic non-food catch-all
        return (9999, "non_food", 0.85, "Not Applicable", f"Non-food product/service - {title}")

    # Rule 3: Alcohol beverages are long_shelf
    if any(keyword in title_lower for keyword in ALCOHOL_KEYWORDS):
        return (180, "long_shelf", 0.95, "Room Temperature/Cool", f"Alcoholic beverage - {title}")

    # Rule 4: Pizza special handling
    if 'pizza' in title_lower:
        if max_gap_days < 14:
            return (5, "short_shelf", 0.90, "Refrigerated", f"Fresh pizza (max_gap={max_gap_days}d)")
        else:
            return (30, "medium_shelf", 0.85, "Frozen/Refrigerated", f"Frozen pizza (max_gap={max_gap_days}d)")

    # Rule 5: Fresh perishables (max_gap < 14 required)
    if not is_not_fresh and any(keyword in title_lower for keyword in FRESH_PERISHABLE_KEYWORDS):
        if 'bowl' in title_lower:
            return (2, "fresh_perishable", 0.90, "Refrigerated", f"Fresh bowl - {title}")
        return (2, "fresh_perishable", 0.90, "Refrigerated", f"Fresh perishable - {title}")

    # Rule 6: Short shelf items (but respect max_gap >= 14 constraint)
    if any(keyword in title_lower for keyword in SHORT_SHELF_KEYWORDS):
        if is_not_fresh:
            # If max_gap >= 14, move to medium_shelf
            return (30, "medium_shelf", 0.80, "Refrigerated/Frozen", f"Extended shelf {title} (max_gap={max_gap_days}d)")
        else:
            return (5, "short_shelf", 0.90, "Refrigerated", f"Short shelf - {title}")

    # Rule 7: Medium shelf items
    if any(keyword in title_lower for keyword in MEDIUM_SHELF_KEYWORDS):
        return (30, "medium_shelf", 0.85, "Refrigerated/Pantry", f"Medium shelf - {title}")

    # Rule 8: Long shelf beverages and dry goods
    if any(keyword in title_lower for keyword in LONG_SHELF_KEYWORDS):
        return (180, "long_shelf", 0.90, "Room Temperature", f"Long shelf beverage/dry good - {title}")

    # Rule 9: Fallback classification based on max_gap_days
    if max_gap_days < 3:
        return (2, "fresh_perishable", 0.6, "Refrigerated", f"Very short gap ({max_gap_days}d) - likely fresh")
    elif max_gap_days < 7:
        return (5, "short_shelf", 0.7, "Refrigerated", f"Short gap ({max_gap_days}d) - likely baked/dairy")
    elif max_gap_days < 14:
        return (7, "short_shelf", 0.65, "Refrigerated", f"Medium gap ({max_gap_days}d) - likely short shelf")
    elif max_gap_days < 60:
        return (30, "medium_shelf", 0.7, "Refrigerated/Frozen", f"Medium gap ({max_gap_days}d) - likely medium shelf")
    else:
        return (180, "long_shelf", 0.75, "Room Temperature", f"Large gap ({max_gap_days}d) - likely long shelf")

def main():
    """Main classification pipeline"""

    print(f"Reading CSV from {INPUT_FILE}...")
    df = pd.read_csv(INPUT_FILE)

    print(f"Total items to classify: {len(df)}")

    # Initialize result columns
    results = {
        'item_id': [],
        'shelf_life_days': [],
        'perishability': [],
        'confidence': [],
        'storage_type': [],
        'notes': []
    }

    # Classify each item
    for idx, row in df.iterrows():
        item_id = row['item_id']
        title = row['title']
        max_gap = row['max_gap_days']

        shelf_days, perishability, confidence, storage, notes = classify_item(
            item_id, title, max_gap
        )

        results['item_id'].append(item_id)
        results['shelf_life_days'].append(shelf_days)
        results['perishability'].append(perishability)
        results['confidence'].append(confidence)
        results['storage_type'].append(storage)
        results['notes'].append(notes)

        if (idx + 1) % 100 == 0:
            print(f"  Classified {idx + 1}/{len(df)} items...")

    # Create output dataframe
    output_df = pd.DataFrame(results)

    # Write to CSV
    print(f"\nWriting results to {OUTPUT_FILE}...")
    output_df.to_csv(OUTPUT_FILE, index=False)

    print(f"✓ Classification complete!")
    print(f"\nSummary Statistics:")
    print(output_df['perishability'].value_counts())
    print(f"\nConfidence distribution:")
    print(output_df['confidence'].describe())
    print(f"\nOutput file: {OUTPUT_FILE}")

if __name__ == '__main__':
    main()
