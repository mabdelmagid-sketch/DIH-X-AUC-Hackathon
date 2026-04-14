import csv

input_file = "/home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting/data/demo/items_to_enrich.csv"
output_file = "/home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting/data/demo/shelf_life_adam_03.csv"


def classify_item(title, description, max_gap_days):
    max_gap_days = float(max_gap_days) if max_gap_days else 0

    title_lower = title.lower() if title else ""
    desc_lower = description.lower() if description else ""
    combined = title_lower + " " + desc_lower

    # Rule: max_gap_days >= 14 means cannot be fresh
    is_not_fresh = max_gap_days >= 14

    # Classification logic
    if any(
        w in combined
        for w in [
            "øl",
            "fadøl",
            "flaske",
            "cider",
            "vin",
            "shots",
            "drinks",
            "beverage",
        ]
    ):
        storage = "ambient"
        shelf_life = 180
        can_freeze = False
        perishability = "low"
        confidence = "high"
        notes = "shelf-stable beverages"
    elif any(
        w in combined
        for w in ["kaffe", "espresso", "cappuccino", "latte", "americano", "te", "chai"]
    ):
        storage = "dry"
        shelf_life = 180
        can_freeze = False
        perishability = "low"
        confidence = "high"
        notes = "dry coffee/tea products"
    elif any(
        w in combined
        for w in [
            "sodavand",
            "vand",
            "cola",
            "pepsi",
            "cocio",
            "juice",
            "saft",
            "kakao",
        ]
    ):
        storage = "ambient"
        shelf_life = 180
        can_freeze = False
        perishability = "low"
        confidence = "high"
        notes = "shelf-stable drinks"
    elif any(w in combined for w in ["pizza"]):
        if is_not_fresh:
            storage = "frozen"
            shelf_life = 90
            can_freeze = True
            perishability = "medium"
        else:
            storage = "refrigerated"
            shelf_life = 2
            can_freeze = True
            perishability = "high"
        confidence = "high"
        notes = "pizza perishable when fresh, can freeze"
    elif any(w in combined for w in ["kebab", "durum", "pita", "-wrap"]):
        if is_not_fresh:
            storage = "frozen"
            shelf_life = 60
            can_freeze = True
            perishability = "medium"
        else:
            storage = "refrigerated"
            shelf_life = 1
            can_freeze = True
            perishability = "high"
        confidence = "high"
        notes = "wrapped sandwiches perishable"
    elif any(w in combined for w in ["burger", "sandwich"]):
        if is_not_fresh:
            storage = "frozen"
            shelf_life = 60
            can_freeze = True
            perishability = "medium"
        else:
            storage = "refrigerated"
            shelf_life = 1
            can_freeze = True
            perishability = "high"
        confidence = "high"
        notes = "sandwiches highly perishable"
    elif any(
        w in combined
        for w in [
            "kylling",
            "chicken",
            "kød",
            "bøf",
            "steak",
            "flæsk",
            "schnitzel",
            "kotelet",
        ]
    ):
        if is_not_fresh:
            storage = "frozen"
            shelf_life = 90
            can_freeze = True
            perishability = "medium"
        else:
            storage = "refrigerated"
            shelf_life = 2
            can_freeze = True
            perishability = "high"
        confidence = "high"
        notes = "meat products"
    elif any(
        w in combined for w in ["fisk", "fiskefilet", "laks", "tun", "rejer", "skaldyr"]
    ):
        if is_not_fresh:
            storage = "frozen"
            shelf_life = 60
            can_freeze = True
            perishability = "medium"
        else:
            storage = "refrigerated"
            shelf_life = 1
            can_freeze = True
            perishability = "high"
        confidence = "high"
        notes = "seafood highly perishable"
    elif any(
        w in combined
        for w in ["pommes", "fritter", "fries", "nuggets", "løgring", "ring"]
    ):
        storage = "frozen"
        shelf_life = 90
        can_freeze = True
        perishability = "low"
        confidence = "high"
        notes = "frozen fried items"
    elif any(
        w in combined for w in ["pølse", "hotdog", "frankfurter", "medister", "ristet"]
    ):
        if is_not_fresh:
            storage = "frozen"
            shelf_life = 60
            can_freeze = True
            perishability = "medium"
        else:
            storage = "refrigerated"
            shelf_life = 3
            can_freeze = True
            perishability = "medium"
        confidence = "high"
        notes = "processed meat"
    elif any(
        w in combined
        for w in ["kage", "tærte", "browne", "macaron", "trøfler", "flødekage"]
    ):
        if is_not_fresh:
            storage = "dry"
            shelf_life = 30
            can_freeze = False
            perishability = "low"
        else:
            storage = "refrigerated"
            shelf_life = 3
            can_freeze = True
            perishability = "medium"
        confidence = "medium"
        notes = "pastries have varying shelf life"
    elif any(w in combined for w in ["brød", "bolle", "morgen", "rugbrød", "surdej"]):
        if is_not_fresh:
            storage = "dry"
            shelf_life = 7
            can_freeze = True
            perishability = "low"
        else:
            storage = "refrigerated"
            shelf_life = 3
            can_freeze = True
            perishability = "medium"
        confidence = "high"
        notes = "bread products"
    elif any(w in combined for w in ["salat", "grøntsag", "tomat", "agurk"]):
        storage = "refrigerated"
        shelf_life = 3
        can_freeze = False
        perishability = "high"
        confidence = "high"
        notes = "fresh salads"
    elif any(
        w in combined
        for w in [
            "pasta",
            "spaghetti",
            "fettucine",
            "penne",
            "gnocchi",
            "tortellini",
            "ravioli",
        ]
    ):
        if is_not_fresh:
            storage = "frozen"
            shelf_life = 60
            can_freeze = True
            perishability = "medium"
        else:
            storage = "refrigerated"
            shelf_life = 2
            can_freeze = True
            perishability = "medium"
        confidence = "medium"
        notes = "pasta dishes"
    elif any(
        w in combined
        for w in ["sauce", "dressing", " mayonnaise", "remoulade", "ketchup"]
    ):
        storage = "refrigerated"
        shelf_life = 14
        can_freeze = False
        perishability = "medium"
        confidence = "high"
        notes = "sauces perishable after opening"
    elif any(w in combined for w in ["ost", "cheese", "mozzarella", "cheddar"]):
        storage = "refrigerated"
        shelf_life = 14
        can_freeze = True
        perishability = "medium"
        confidence = "high"
        notes = "cheese refrigerated"
    elif any(w in combined for w in ["buffet", "aften", "frokost"]):
        storage = "refrigerated"
        shelf_life = 1
        can_freeze = False
        perishability = "high"
        confidence = "medium"
        notes = "ready to eat meals"
    elif any(w in combined for w in ["smørrebrød", "åbent"]):
        storage = "refrigerated"
        shelf_life = 1
        can_freeze = False
        perishability = "high"
        confidence = "high"
        notes = "open sandwiches highly perishable"
    else:
        if is_not_fresh:
            storage = "ambient"
            shelf_life = 30
            can_freeze = False
            perishability = "low"
            confidence = "low"
            notes = "assumed shelf-stable"
        else:
            storage = "refrigerated"
            shelf_life = 2
            can_freeze = True
            perishability = "medium"
            confidence = "low"
            notes = "assumed perishable"

    return {
        "storage_type": storage,
        "shelf_life_days": shelf_life,
        "can_freeze": can_freeze,
        "perishability": perishability,
        "confidence": confidence,
        "notes": notes,
    }


# Read source data
with open(input_file, "r", encoding="utf-8") as f:
    reader = csv.reader(f)
    rows = list(reader)

# Get rows 1524-2285 (indices 1523-2284)
data_rows = rows[1523:2285]

# Process and write output
output_rows = [
    [
        "title",
        "description",
        "max_gap_days",
        "storage_type",
        "shelf_life_days",
        "can_freeze",
        "perishability",
        "confidence",
        "notes",
    ]
]

for row in data_rows:
    if len(row) >= 13:
        item_id = row[0]
        description = row[1] if len(row) > 1 else ""
        title = row[2] if len(row) > 2 else ""
        max_gap_days = row[11] if len(row) > 11 else "0"

        result = classify_item(title, description, max_gap_days)

        output_rows.append(
            [
                title,
                description[:50] + "..." if len(description) > 50 else description,
                max_gap_days,
                result["storage_type"],
                result["shelf_life_days"],
                result["can_freeze"],
                result["perishability"],
                result["confidence"],
                result["notes"],
            ]
        )

with open(output_file, "w", encoding="utf-8", newline="") as f:
    writer = csv.writer(f)
    writer.writerows(output_rows)

print(f"Processed {len(output_rows) - 1} rows")
