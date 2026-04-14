#!/usr/bin/env python3
"""
Danish Food/Product Classifier
Classifies items into food and non-food categories with shelf life estimates
"""

import pandas as pd
import re
from pathlib import Path

# Define Danish product keywords
DANISH_KEYWORDS = {
    # Non-food services
    'non_food': [
        'klip', 'klipp', 'barber', 'massage', 'olie massage', 'aromamassage', 'fodmassage',
        'manicure', 'pedicure', 'shellac', 'hårbehandling', 'hårvasker', 'frisør',
        'reparation', 'service', 'entré', 'billet', 'gavekort', 'gift card', 'rabatkort',
        'diskontkort', 'medlemskab', 'pant', 'kaution', 'deposit', 'røg', 'cigarette',
        'cigar', 'tøj', 'tøjstykke', 'bukser', 'skjorte', 'kjoler', 'badminton',
        'fitness', 'træning', 'coaching', 'undervisning', 'lektie', 'håndelp',
        'fringe', 'styling', 'behandling', 'konsultation', 'terapeu', 'psykolog',
        'tandlæge', 'læge', 'terapeut', 'time', 'time massage', 'akupunktur',
    ],

    # Long shelf life drinks and alcohol
    'long_shelf_drinks': [
        'tuborg', 'carlsberg', 'sommersby', 'mokai', 'energidrik', 'redbull', 'energy',
        'cola', 'pepsi', 'fanta', 'sprite', 'beer', 'øl', 'lager', 'ipa', 'pale ale',
        'stout', 'porter', 'cider', 'vin', 'wine', 'prosecco', 'champagne', 'cognac',
        'whisky', 'brandy', 'vodka', 'gin', 'rom', 'rum', 'tequila', 'likør', 'schnaps',
        'sake', 'mead', 'perry', 'saft', 'juice', 'drik', 'cocio', 'kakao',
        'the', 'te', 'kaffe', 'coffee', 'espresso', 'cappuccino', 'latte', 'mokka',
        'sirup', 'syrup', 'shot', 'long drink', 'cocktail', 'mixtur', 'punch',
        '1664', 'brooklyn', 'grimbergen', 'jacobsen', 'mikkeller', 'mikkele',
        'burst', 'raspy', 'rascal', 'passion', 'attraction', 'blond',
        'belgisk', 'pilsner', 'hvidtøl', 'bryglab', 'basil', 'sour', 'smash',
        'oprah', 'antonis', 'ørientalske', 'adelhardt', 'adelhard', 'rabarber',
        'playa de brooklyn', 'vesuvio',
    ],

    # Bread and bakery
    'short_shelf_bread': [
        'brød', 'brødet', 'rugbrød', 'hvedebrød', 'franskbrød', 'ciabatta',
        'baguette', 'focaccia', 'rundstykker', 'boller', 'kanelsnurre', 'croissant',
        'wienerbrød', 'æbleskiver', 'kransekage', 'flødeboller', 'flødeis', 'is',
        'softice', 'softis', 'cookie', 'cookies', 'småkage', 'biscuit', 'kager',
        'tærte', 'kage', 'lagkage', 'drømmekage', 'hindbærsnitter',
        'barcelona', 'chokoladeemne', 'chokolade', 'lakrids', 'konfekt', 'drops',
        'gummibjørne', 'rugbrød', 'knækbrød', 'frø og nød', 'granola',
        'napoleonshat',
    ],

    # Prepared/cooked meals
    'short_shelf_meals': [
        'håndmad', 'smørrebrød', 'smørrebrod', 'sandwich', 'toastmenu', 'brunch',
        'lunch', 'middag', 'frikadelle', 'frikadeller', 'kød', 'kødbouillon',
        'pølse', 'pølser', 'pølsemad', 'rullepølse', 'lever', 'leverpostej',
        'mælkepølse', 'kalvepølse', 'kalkun', 'kylling', 'høne',
        'steg', 'roast', 'ragu', 'bouillabaisse', 'sancocho', 'pilaf', 'risotto',
        'pasta', 'nudler', 'noodles', 'quiche', 'omelet', 'æggeret', 'æggekage',
        'gratin', 'lasagne', 'bolognese', 'carbonara', 'frikasse', 'stuvning',
        'skind', 'goulash', 'stegt', 'dampet', 'grillet', 'kogt', 'rosted',
        'soupe', 'suppe', 'bouillon', 'konsommé', 'ret', 'menu', 'mål',
        'salade', 'salat', 'salatmenu',
    ],

    # Dairy and cheese
    'medium_shelf_dairy': [
        'ost', 'cheese', 'smør', 'butter', 'margarine', 'mælk', 'milk',
        'kærnemælk', 'buttermilk', 'yoghurt', 'yougurt', 'filmjølk', 'fløde',
        'crème', 'créme', 'cream', 'créme fraîche', 'sødmælk', 'skummetmælk',
        'gedeost', 'blåost', 'brie', 'camembert', 'tilsiter', 'havarti',
        'danbo', 'sammens', 'feta', 'gorgonzola', 'roquefort', 'västerbotten',
    ],

    # Pizza patterns
    'pizza': [
        'pizza', 'margherita', 'hawaii', 'vesuvio', 'pepperoni', 'quattro',
        'quattro formaggi', 'kebab', 'bbq', 'diavolo', 'inferno', 'caprese',
        'carbonara', 'prosciutto', 'bosco', 'verde', 'rossa', 'bianca',
    ],

    # Processed/cured meats and medium shelf
    'medium_shelf_processed': [
        'spaghetti', 'makaroni', 'penne', 'farfalle', 'risoni', 'orzo',
        'mel', 'sukker', 'salt', 'basilikum', 'oregano', 'timian', 'rosemarin',
        'blommer', 'tørret frugt', 'rosiner', 'sultanas', 'korender', 'dadler',
        'nødder', 'mandler', 'kastanjer', 'pistacier', 'jordnødder', 'peanuts',
        'sunflowerkerner', 'græskar kerner', 'fløreskinner', 'konserveret',
        'dåsemad', 'marmelade', 'syltetøj', 'konfityrer', 'honning',
        'farina', 'stivelse', 'hvedemel', 'rugmel', 'maizena', 'kartoffelmel',
        'bagepulver', 'gær', 'bageindtægt', 'sukkerart', 'stevia', 'sorbitol',
        'sauce', 'pesto', 'hummus', 'dip', 'dressing', 'mayonnaise', 'ketchup',
        'sennep', 'mustard', 'senap', 'worcester', 'soja', 'tamari', 'dashi',
        'fiskesauce', 'olie', 'olivenolie', 'rapsolie', 'solsikkeolie', 'kokosolie',
        'eddike', 'vinegar', 'hvidvinseddike', 'røvinseddike',
        'balsamico', 'appelsineddike', 'rosineeddike', 'æbleeddike', 'malteddike',
        'sylteblandinger', 'brød maling', 'mel dej', 'brød mel', 'panko',
        'leverpostej', 'pâté', 'terrine', 'rillettes', 'forcemeat',
        'spegepølse', 'salami', 'prosciutto', 'serrano', 'parma', 'jamón',
        'pancetta', 'guanciale', 'andouille', 'chorizo', 'kielbasa', 'salsiccia',
        'mortadella', 'braunschweiger', 'leberwurst', 'blutwurst', 'souse',
        'corned beef', 'beef jerky', 'biltong', 'pemmican', 'dried meat',
    ],

    # Frozen and long shelf
    'long_shelf_frozen': [
        'frossen', 'frosset', 'is', 'softice', 'fryser', 'frysevare',
        'frysevarepartiet', 'frosne frugter', 'frosne grøntsager', 'frosne kartofler',
        'pommes', 'fries', 'frites', 'chips', 'kartoffelmos',
    ],

    # Snacks and candy
    'long_shelf_snacks': [
        'chips', 'kartoffelchips', 'popkorn', 'solsikkekerner',
        'gummibjørne', 'lakrids', 'gummi', 'tygge',
        'lollipop', 'slikkepind', 'karameller', 'dropper', 'pibetobak',
        'chokolade', 'chokolader', 'schokolade', 'snickers', 'mars', 'twix',
        'kinder', 'lindor', 'ferrero', 'rocher', 'lindt', 'ghirardelli',
        'cadbury', 'milka', 'côte d\'or', 'godiva', 'toblerone', 'bounty',
        'butterfinger', 'laffy taffy', 'nerds', 'skittles', 'starburst', 'milky way',
        'krispie', 'corn flakes', 'müesli', 'granola', 'haferflocken', 'oatmeal',
        'kellogs', 'nesquik', 'cacao', 'ovomaltine', 'horlicks', 'bamse',
    ],

    # Unspecified default
    'unspecified': ['unspecified', 'special'],
}

def get_max_gap_category(max_gap):
    """Determine shelf life category based on max_gap_days"""
    if pd.isna(max_gap):
        return 14  # Default unspecified

    max_gap = float(max_gap)
    if max_gap >= 1000:  # Services
        return 9999
    elif max_gap >= 90:
        return 'long_shelf'
    elif max_gap >= 14:
        return 'medium_shelf'
    elif max_gap >= 3:
        return 'short_shelf'
    else:
        return 'fresh_perishable'

def classify_item(item_id, title, max_gap_days):
    """Classify a single item based on title and max_gap_days"""

    if pd.isna(title) or title == '':
        return {
            'item_id': item_id,
            'shelf_life_days': 14,
            'perishability': 'medium',
            'confidence': 'low',
            'storage_type': 'ambient',
            'notes': 'Empty title'
        }

    title_lower = str(title).lower().strip()

    # Check for non-food services
    for keyword in DANISH_KEYWORDS['non_food']:
        if keyword in title_lower:
            return {
                'item_id': item_id,
                'shelf_life_days': 9999,
                'perishability': 'low',
                'confidence': 'high',
                'storage_type': 'non_food',
                'notes': f'Service/non-food: {title}'
            }

    # Check for drinks/alcohol first (high priority)
    for keyword in DANISH_KEYWORDS['long_shelf_drinks']:
        if keyword in title_lower:
            shelf_life = 365
            storage = 'ambient'
            if any(x in title_lower for x in ['kakao', 'the', 'te', 'kaffe', 'coffee']):
                storage = 'dry'
            elif any(x in title_lower for x in ['saft', 'juice', 'latte', 'cappuccino']):
                storage = 'refrigerated'

            return {
                'item_id': item_id,
                'shelf_life_days': shelf_life,
                'perishability': 'low',
                'confidence': 'high',
                'storage_type': storage,
                'notes': f'Beverage/alcohol: {title}'
            }

    # Check for pizza
    for keyword in DANISH_KEYWORDS['pizza']:
        if keyword in title_lower:
            # If max_gap < 14, treat as short shelf; else medium
            if float(max_gap_days) < 14:
                return {
                    'item_id': item_id,
                    'shelf_life_days': 3,
                    'perishability': 'high',
                    'confidence': 'high',
                    'storage_type': 'refrigerated',
                    'notes': f'Fresh pizza: {title}'
                }
            else:
                return {
                    'item_id': item_id,
                    'shelf_life_days': 30,
                    'perishability': 'medium',
                    'confidence': 'high',
                    'storage_type': 'frozen',
                    'notes': f'Frozen pizza: {title}'
                }

    # Check for bread/bakery
    for keyword in DANISH_KEYWORDS['short_shelf_bread']:
        if keyword in title_lower:
            # Distinguish between cookies/long-shelf and fresh bakery
            if any(x in title_lower for x in ['cookie', 'cookies', 'småkage', 'biscuit', 'lakrids', 'drops', 'gummibjørne']):
                return {
                    'item_id': item_id,
                    'shelf_life_days': 90,
                    'perishability': 'low',
                    'confidence': 'high',
                    'storage_type': 'dry',
                    'notes': f'Shelf-stable bakery: {title}'
                }
            else:
                return {
                    'item_id': item_id,
                    'shelf_life_days': 5,
                    'perishability': 'high',
                    'confidence': 'high',
                    'storage_type': 'ambient',
                    'notes': f'Fresh bread/bakery: {title}'
                }

    # Check for prepared meals (include salads)
    for keyword in DANISH_KEYWORDS['short_shelf_meals']:
        if keyword in title_lower:
            if 'salat' in title_lower or 'salade' in title_lower or 'salatmenu' in title_lower:
                shelf_life = 2
            else:
                shelf_life = 3
            return {
                'item_id': item_id,
                'shelf_life_days': shelf_life,
                'perishability': 'high',
                'confidence': 'high',
                'storage_type': 'refrigerated',
                'notes': f'Prepared meal/salad: {title}'
            }

    # Check for dairy
    for keyword in DANISH_KEYWORDS['medium_shelf_dairy']:
        if keyword in title_lower:
            if 'mælk' in title_lower or 'milk' in title_lower or 'kærnemælk' in title_lower:
                shelf_life = 7
            elif 'yoghurt' in title_lower or 'yougurt' in title_lower:
                shelf_life = 21
            elif 'smør' in title_lower or 'butter' in title_lower:
                shelf_life = 60
            else:
                shelf_life = 30

            return {
                'item_id': item_id,
                'shelf_life_days': shelf_life,
                'perishability': 'medium',
                'confidence': 'high',
                'storage_type': 'refrigerated',
                'notes': f'Dairy: {title}'
            }

    # Check for processed/medium shelf
    for keyword in DANISH_KEYWORDS['medium_shelf_processed']:
        if keyword in title_lower:
            return {
                'item_id': item_id,
                'shelf_life_days': 30,
                'perishability': 'low',
                'confidence': 'medium',
                'storage_type': 'dry' if 'olie' not in title_lower else 'ambient',
                'notes': f'Processed food: {title}'
            }

    # Default classification based on max_gap_days
    gap_category = get_max_gap_category(max_gap_days)

    if gap_category == 'long_shelf':
        return {
            'item_id': item_id,
            'shelf_life_days': 180,
            'perishability': 'low',
            'confidence': 'medium',
            'storage_type': 'dry',
            'notes': f'Long shelf (max_gap {max_gap_days}): {title}'
        }
    elif gap_category == 'medium_shelf':
        return {
            'item_id': item_id,
            'shelf_life_days': 30,
            'perishability': 'medium',
            'confidence': 'medium',
            'storage_type': 'ambient',
            'notes': f'Medium shelf (max_gap {max_gap_days}): {title}'
        }
    elif gap_category == 'short_shelf':
        return {
            'item_id': item_id,
            'shelf_life_days': 5,
            'perishability': 'medium',
            'confidence': 'low',
            'storage_type': 'refrigerated',
            'notes': f'Short shelf (max_gap {max_gap_days}): {title}'
        }
    else:  # fresh_perishable
        return {
            'item_id': item_id,
            'shelf_life_days': 2,
            'perishability': 'high',
            'confidence': 'low',
            'storage_type': 'refrigerated',
            'notes': f'Fresh perishable (max_gap {max_gap_days}): {title}'
        }

def main():
    # Read input CSV
    input_file = Path('/home/yahyahammoudeh/Documents/loving loyalty internship/data/raw/haiku_mega_0.csv')
    output_file = Path('/home/yahyahammoudeh/Documents/loving loyalty internship/data/raw/haiku_result_0.csv')

    print(f"Reading from: {input_file}")
    df = pd.read_csv(input_file)

    print(f"Total items: {len(df)}")

    # Classify all items
    results = []
    for idx, row in df.iterrows():
        result = classify_item(row['item_id'], row['title'], row['max_gap_days'])
        results.append(result)

        if (idx + 1) % 100 == 0:
            print(f"Classified {idx + 1}/{len(df)} items...")

    # Create results dataframe
    results_df = pd.DataFrame(results)

    # Ensure correct column order
    results_df = results_df[['item_id', 'shelf_life_days', 'perishability', 'confidence', 'storage_type', 'notes']]

    # Write output CSV
    results_df.to_csv(output_file, index=False)
    print(f"\nResults written to: {output_file}")
    print(f"Total items classified: {len(results_df)}")

    # Print summary statistics
    print("\nClassification Summary:")
    print(f"Storage types:")
    print(results_df['storage_type'].value_counts())
    print(f"\nPerishability distribution:")
    print(results_df['perishability'].value_counts())
    print(f"\nConfidence distribution:")
    print(results_df['confidence'].value_counts())

    return 0

if __name__ == '__main__':
    exit(main())
