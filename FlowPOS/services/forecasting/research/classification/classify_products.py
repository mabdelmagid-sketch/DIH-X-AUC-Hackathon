#!/usr/bin/env python3
"""
Danish food product classifier based on title and max_gap_days.
Classifies products into perishability categories with shelf life estimates.
"""

import pandas as pd
import re
from pathlib import Path

# Configuration
INPUT_FILE = Path("/home/yahyahammoudeh/Documents/loving loyalty internship/data/raw/haiku_mega_9.csv")
OUTPUT_FILE = Path("/home/yahyahammoudeh/Documents/loving loyalty internship/data/raw/haiku_result_9.csv")

# Non-food keywords (services, non-edible items)
NON_FOOD_KEYWORDS = {
    'klip', 'haircut', 'massage', 'masage', 'repair', 'reparation',
    'entré', 'entre', 'gavekort', 'giftcard', 'rabatkort', 'discount',
    'activity', 'aktivitet', 'røg', 'cigar', 'cigarette', 'pant',
    'clothing', 'clothes', 'tøj', 'servering', 'service'
}

# Fresh perishable keywords (shelf_life=1-2d)
FRESH_PERISHABLE = {
    'sandwich', 'sushi', 'salat', 'salad', 'råret', 'raw',
    'fersk', 'fresh', 'deli'
}

# Short shelf keywords (shelf_life=3-7d)
SHORT_SHELF = {
    'pizza', 'flute', 'bagel', 'brød', 'bread', 'croissant',
    'pastry', 'kage', 'cake', 'yoghurt', 'yogurt', 'smør', 'butter',
    'ost', 'cheese', 'fløde', 'cream', 'mælk', 'milk', 'mad', 'meal',
    'ret', 'dish', 'gryde', 'stew'
}

# Long shelf keywords (shelf_life=90-365d)
LONG_SHELF_KEYWORDS = {
    'øl', 'beer', 'vin', 'wine', 'spiritus', 'spirit', 'whisky', 'vodka', 'rom', 'rum',
    'kaffe', 'coffee', 'te', 'tea', 'kakao', 'cocoa', 'chokolade', 'chocolate',
    'cola', 'fanta', 'sprite', 'drink', 'drik', 'saft', 'juice', 'energi',
    'candy', 'slik', 'chokolade', 'nut', 'nød', 'chip', 'snack', 'kringle',
    'konserve', 'canned', 'dåse', 'tør', 'dry', 'tørret', 'dried', 'sukker',
    'salt', 'krydderi', 'spice', 'mel', 'flour', 'olie', 'oil', 'essens',
    'sirup', 'honey', 'honning', 'nougat'
}

# Medium shelf keywords (shelf_life=14-60d)
MEDIUM_SHELF_KEYWORDS = {
    'ost', 'cheese', 'leverpostej', 'pâté', 'skinke', 'ham', 'kødt', 'meat',
    'corned', 'flæsk', 'bacon', 'sild', 'herring', 'fisk', 'fish', 'dej',
    'dough', 'butter', 'marmelade', 'jam', 'kompot', 'confiture', 'sauce',
    'dressing', 'dip', 'påsmørning', 'spread', 'syltetøj', 'konfityre'
}

def classify_product(item_id, title, max_gap_days):
    """
    Classify a single product based on title and max_gap_days.
    Returns: (shelf_life_days, perishability, confidence, storage_type, notes)
    """

    title_lower = str(title).lower().strip()
    confidence = 0.9  # Default high confidence
    notes = []

    # Handle missing/unspecified products
    if title_lower == 'unspecified':
        return (14, 'medium_shelf', 0.5, 'ambient', 'Unspecified product - default to 14 days')

    # Check for non-food items first
    for keyword in NON_FOOD_KEYWORDS:
        if keyword in title_lower:
            return (9999, 'non_food', 0.95, 'n/a', f'Non-food item: service/non-edible')

    # Check for fresh perishable items
    for keyword in FRESH_PERISHABLE:
        if keyword in title_lower:
            if max_gap_days >= 14:
                # Not actually fresh if gap is large
                return (14, 'medium_shelf', 0.7, 'refrigerated', f'Named fresh but gap={max_gap_days}d suggests medium shelf')
            return (2, 'fresh_perishable', 0.95, 'refrigerated', f'Fresh perishable: {keyword}')

    # Special handling for pizza
    if 'pizza' in title_lower:
        if max_gap_days < 14:
            return (5, 'short_shelf', 0.95, 'refrigerated', 'Pizza: short shelf life')
        else:
            return (30, 'medium_shelf', 0.9, 'frozen/refrigerated', 'Pizza: frozen variety with longer gap')

    # Special handling for beer/wine/spirits
    if any(keyword in title_lower for keyword in ['øl', 'beer', 'vin', 'wine', 'spiritus', 'spirit']):
        return (365, 'long_shelf', 0.98, 'ambient', 'Alcoholic beverage')

    # Check for long shelf items
    for keyword in LONG_SHELF_KEYWORDS:
        if keyword in title_lower:
            return (180, 'long_shelf', 0.95, 'ambient', f'Long shelf item: {keyword}')

    # Check for short shelf items
    for keyword in SHORT_SHELF:
        if keyword in title_lower:
            if max_gap_days >= 14:
                return (30, 'medium_shelf', 0.8, 'refrigerated', f'{keyword} - gap suggests longer shelf')
            return (5, 'short_shelf', 0.95, 'refrigerated', f'Short shelf: {keyword}')

    # Check for medium shelf items
    for keyword in MEDIUM_SHELF_KEYWORDS:
        if keyword in title_lower:
            return (30, 'medium_shelf', 0.95, 'refrigerated', f'Medium shelf: {keyword}')

    # Fallback logic based on max_gap_days
    if max_gap_days >= 14:
        if max_gap_days >= 90:
            return (180, 'long_shelf', 0.6, 'ambient', f'Long gap ({max_gap_days}d) suggests long shelf')
        else:
            return (30, 'medium_shelf', 0.6, 'refrigerated/ambient', f'Medium gap ({max_gap_days}d) suggests medium shelf')
    else:
        # Short gap (< 14 days)
        if max_gap_days <= 2:
            return (2, 'fresh_perishable', 0.6, 'refrigerated', f'Very short gap ({max_gap_days}d) suggests fresh')
        elif max_gap_days <= 7:
            return (5, 'short_shelf', 0.6, 'refrigerated', f'Short gap ({max_gap_days}d) suggests short shelf')
        else:
            return (7, 'short_shelf', 0.6, 'refrigerated', f'Moderate gap ({max_gap_days}d) suggests short shelf')

def main():
    # Read input CSV
    df = pd.read_csv(INPUT_FILE)

    # Apply classification
    results = []
    for idx, row in df.iterrows():
        item_id = row['item_id']
        title = row['title']
        max_gap_days = row['max_gap_days']

        shelf_life_days, perishability, confidence, storage_type, notes = classify_product(
            item_id, title, max_gap_days
        )

        results.append({
            'item_id': item_id,
            'shelf_life_days': shelf_life_days,
            'perishability': perishability,
            'confidence': confidence,
            'storage_type': storage_type,
            'notes': notes
        })

    # Create output dataframe
    output_df = pd.DataFrame(results)

    # Write to CSV
    output_df.to_csv(OUTPUT_FILE, index=False)

    # Print summary statistics
    print(f"Classification complete!")
    print(f"Total items: {len(output_df)}")
    print(f"\nDistribution by perishability:")
    print(output_df['perishability'].value_counts())
    print(f"\nDistribution by shelf life days:")
    print(output_df['shelf_life_days'].value_counts().sort_index())
    print(f"\nAverage confidence: {output_df['confidence'].mean():.3f}")
    print(f"\nOutput written to: {OUTPUT_FILE}")

if __name__ == '__main__':
    main()
