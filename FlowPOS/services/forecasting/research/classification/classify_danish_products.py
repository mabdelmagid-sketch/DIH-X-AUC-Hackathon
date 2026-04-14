import pandas as pd
import re
from pathlib import Path

# Read the CSV
input_path = "/home/yahyahammoudeh/Documents/loving loyalty internship/data/raw/haiku_mega_5.csv"
output_path = "/home/yahyahammoudeh/Documents/loving loyalty internship/data/raw/haiku_result_5.csv"

df = pd.read_csv(input_path)

# Initialize output columns
classifications = []

for idx, row in df.iterrows():
    item_id = row['item_id']
    title = str(row['title']).strip()
    max_gap = row['max_gap_days']

    # Initialize classification
    shelf_life_days = 14  # default
    perishability = "medium_shelf"
    confidence = "high"
    storage_type = "ambient"
    notes = ""

    # Check if it's "Unspecified"
    if title.lower() == "unspecified":
        shelf_life_days = 14
        perishability = "medium_shelf"
        confidence = "low"
        storage_type = "unknown"
        notes = "Unspecified product"

    # Non-food items (services, clothing, etc.)
    elif any(keyword in title.lower() for keyword in [
        'klip', 'barber', 'haircut', 'massage', 'repair', 'entré', 'gavekort',
        'gift card', 'clothing', 'røg', 'rabatkort', 'discount card', 'activity',
        'pant', 'deposit', 'iphone', 'mobil', 'phone', 'case', 'cover', 'kabler',
        'cables', 'opladere', 'charger', 'power bank'
    ]):
        shelf_life_days = 9999
        perishability = "non_food"
        storage_type = "non_food"
        notes = "Service or non-food item"

    # Beer, wine, spirits (long shelf)
    elif any(keyword in title.lower() for keyword in [
        'beer', 'øl', 'ale', 'lager', 'pilsner', 'fad', 'wine', 'vin', 'rose',
        'spirit', 'snaps', 'vodka', 'whisky', 'rum', 'gin', 'tequila'
    ]):
        shelf_life_days = 365
        perishability = "long_shelf"
        storage_type = "cool_dark"
        notes = "Alcoholic beverage"

    # Pizza (special rule)
    elif 'pizza' in title.lower():
        if max_gap < 14:
            shelf_life_days = 3
            perishability = "short_shelf"
            storage_type = "refrigerated"
            notes = "Pizza - short shelf life"
        else:
            shelf_life_days = 30
            perishability = "medium_shelf"
            storage_type = "frozen"
            notes = "Pizza - medium shelf (frozen)"

    # Fresh perishables (max_gap < 14 and items indicating freshness)
    elif max_gap < 14 and any(keyword in title.lower() for keyword in [
        'sushi', 'sandwich', 'salad', 'frisk', 'rå', 'raw', 'sallad', 'smørrebrød',
        'chapati', 'rolex', 'vegan', 'jerk', 'quesadilla', 'tacos', 'birria',
        'onion rings', 'plantain', 'meat', 'pork', 'fish', 'seafood', 'deli'
    ]):
        shelf_life_days = 2
        perishability = "fresh_perishable"
        storage_type = "refrigerated"
        notes = "Fresh prepared food"

    # Short shelf items (bread, pastries, cooked meals, dairy)
    elif any(keyword in title.lower() for keyword in [
        'brød', 'bread', 'bager', 'pastry', 'kage', 'cake', 'mælk', 'milk',
        'yogurt', 'smør', 'butter', 'ost', 'cheese', 'fløde', 'cream', 'dressing'
    ]):
        shelf_life_days = 5
        perishability = "short_shelf"
        storage_type = "refrigerated"
        notes = "Bread, pastry or dairy product"

    # Beverages and dry goods (long shelf)
    elif any(keyword in title.lower() for keyword in [
        'drinkable', 'drink', 'drik', 'juice', 'saft', 'vand', 'water', 'kaffe',
        'coffee', 'te', 'tea', 'kiks', 'cookie', 'chips', 'snack', 'chocolate',
        'chokolade', 'candy', 'slik', 'marmelade', 'jam', 'conserve', 'canned',
        'konserves', 'pasta', 'ris', 'rice', 'mel', 'flour'
    ]):
        shelf_life_days = 180
        perishability = "long_shelf"
        storage_type = "ambient"
        notes = "Beverages or dry goods"

    # Sauces, processed foods (medium shelf)
    elif any(keyword in title.lower() for keyword in [
        'sauce', 'oil', 'olie', 'essense', 'spice', 'krydderi', 'frozen', 'frosset'
    ]):
        shelf_life_days = 30
        perishability = "medium_shelf"
        storage_type = "ambient_or_frozen"
        notes = "Processed item or condiment"

    # Default logic based on max_gap
    else:
        if max_gap < 3:
            shelf_life_days = 2
            perishability = "fresh_perishable"
            storage_type = "refrigerated"
        elif max_gap < 14:
            shelf_life_days = 5
            perishability = "short_shelf"
            storage_type = "refrigerated"
        elif max_gap < 60:
            shelf_life_days = 30
            perishability = "medium_shelf"
            storage_type = "ambient"
        else:
            shelf_life_days = 180
            perishability = "long_shelf"
            storage_type = "ambient"
        notes = f"Classified by max_gap_days={max_gap}"

    classifications.append({
        'item_id': item_id,
        'shelf_life_days': shelf_life_days,
        'perishability': perishability,
        'confidence': confidence,
        'storage_type': storage_type,
        'notes': notes
    })

# Create output dataframe
result_df = pd.DataFrame(classifications)

# Write to CSV
result_df.to_csv(output_path, index=False)

print(f"Classification complete!")
print(f"Processed {len(result_df)} items")
print(f"\nClassification Summary:")
print(result_df['perishability'].value_counts())
print(f"\nOutput saved to: {output_path}")
print(f"\nFirst 10 rows:")
print(result_df.head(10))
