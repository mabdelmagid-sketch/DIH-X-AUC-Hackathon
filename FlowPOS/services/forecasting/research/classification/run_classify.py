import csv

input_file = "/home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting/data/demo/items_to_enrich.csv"
output_file = "/home/yahyahammoudeh/Documents/Dih/DIH-X-AUC-Hackathon/FlowPOS/services/forecasting/data/demo/shelf_life_adam_03.csv"

with open(input_file, "r", encoding="utf-8") as f:
    reader = csv.reader(f)
    rows = list(reader)

data_rows = rows[1523:2285]

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

        title_lower = title.lower() if title else ""
        desc_lower = description.lower() if description else ""
        combined = title_lower + " " + desc_lower

        is_not_fresh = float(max_gap_days) >= 14 if max_gap_days else False

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
            storage, shelf_life, can_freeze, perish, conf, notes = (
                "ambient",
                180,
                False,
                "low",
                "high",
                "shelf-stable beverages",
            )
        elif any(
            w in combined
            for w in [
                "kaffe",
                "espresso",
                "cappuccino",
                "latte",
                "americano",
                "te",
                "chai",
            ]
        ):
            storage, shelf_life, can_freeze, perish, conf, notes = (
                "dry",
                180,
                False,
                "low",
                "high",
                "dry coffee/tea products",
            )
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
            storage, shelf_life, can_freeze, perish, conf, notes = (
                "ambient",
                180,
                False,
                "low",
                "high",
                "shelf-stable drinks",
            )
        elif any(w in combined for w in ["pizza"]):
            if is_not_fresh:
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "frozen",
                    90,
                    True,
                    "medium",
                    "high",
                    "pizza can be frozen",
                )
            else:
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "refrigerated",
                    2,
                    True,
                    "high",
                    "high",
                    "pizza perishable when fresh",
                )
        elif any(w in combined for w in ["kebab", "durum", "pita", "wrap"]):
            if is_not_fresh:
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "frozen",
                    60,
                    True,
                    "medium",
                    "high",
                    "wrapped sandwiches can freeze",
                )
            else:
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "refrigerated",
                    1,
                    True,
                    "high",
                    "high",
                    "wrapped sandwiches highly perishable",
                )
        elif any(w in combined for w in ["burger", "sandwich"]):
            if is_not_fresh:
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "frozen",
                    60,
                    True,
                    "medium",
                    "high",
                    "burgers can freeze",
                )
            else:
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "refrigerated",
                    1,
                    True,
                    "high",
                    "high",
                    "sandwiches highly perishable",
                )
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
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "frozen",
                    90,
                    True,
                    "medium",
                    "high",
                    "meat can be frozen",
                )
            else:
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "refrigerated",
                    2,
                    True,
                    "high",
                    "high",
                    "meat products",
                )
        elif any(
            w in combined
            for w in ["fisk", "fiskefilet", "laks", "tun", "rejer", "skaldyr"]
        ):
            if is_not_fresh:
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "frozen",
                    60,
                    True,
                    "medium",
                    "high",
                    "seafood can freeze",
                )
            else:
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "refrigerated",
                    1,
                    True,
                    "high",
                    "high",
                    "seafood highly perishable",
                )
        elif any(
            w in combined
            for w in ["pommes", "fritter", "fries", "nuggets", "løgring", "ring"]
        ):
            storage, shelf_life, can_freeze, perish, conf, notes = (
                "frozen",
                90,
                True,
                "low",
                "high",
                "frozen fried items",
            )
        elif any(
            w in combined
            for w in ["pølse", "hotdog", "frankfurter", "medister", "ristet"]
        ):
            if is_not_fresh:
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "frozen",
                    60,
                    True,
                    "medium",
                    "high",
                    "processed meat can freeze",
                )
            else:
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "refrigerated",
                    3,
                    True,
                    "medium",
                    "high",
                    "processed meat",
                )
        elif any(
            w in combined
            for w in ["kage", "tærte", "browne", "macaron", "trøfler", "flødekage"]
        ):
            if is_not_fresh:
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "dry",
                    30,
                    False,
                    "low",
                    "medium",
                    "pastries shelf-stable",
                )
            else:
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "refrigerated",
                    3,
                    True,
                    "medium",
                    "medium",
                    "pastries perishable",
                )
        elif any(
            w in combined for w in ["brød", "bolle", "morgen", "rugbrød", "surdej"]
        ):
            if is_not_fresh:
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "dry",
                    7,
                    True,
                    "low",
                    "high",
                    "bread products",
                )
            else:
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "refrigerated",
                    3,
                    True,
                    "medium",
                    "high",
                    "bread products",
                )
        elif any(w in combined for w in ["salat", "grøntsag", "tomat", "agurk"]):
            storage, shelf_life, can_freeze, perish, conf, notes = (
                "refrigerated",
                3,
                False,
                "high",
                "high",
                "fresh salads",
            )
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
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "frozen",
                    60,
                    True,
                    "medium",
                    "medium",
                    "pasta dishes can freeze",
                )
            else:
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "refrigerated",
                    2,
                    True,
                    "medium",
                    "medium",
                    "pasta dishes",
                )
        elif any(
            w in combined
            for w in ["sauce", "dressing", "mayonnaise", "remoulade", "ketchup"]
        ):
            storage, shelf_life, can_freeze, perish, conf, notes = (
                "refrigerated",
                14,
                False,
                "medium",
                "high",
                "sauces perishable",
            )
        elif any(w in combined for w in ["ost", "cheese", "mozzarella", "cheddar"]):
            storage, shelf_life, can_freeze, perish, conf, notes = (
                "refrigerated",
                14,
                True,
                "medium",
                "high",
                "cheese refrigerated",
            )
        elif any(w in combined for w in ["buffet", "aften", "frokost"]):
            storage, shelf_life, can_freeze, perish, conf, notes = (
                "refrigerated",
                1,
                False,
                "high",
                "medium",
                "ready to eat meals",
            )
        elif any(w in combined for w in ["smørrebrød", "åbent"]):
            storage, shelf_life, can_freeze, perish, conf, notes = (
                "refrigerated",
                1,
                False,
                "high",
                "high",
                "open sandwiches",
            )
        else:
            if is_not_fresh:
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "ambient",
                    30,
                    False,
                    "low",
                    "low",
                    "assumed shelf-stable",
                )
            else:
                storage, shelf_life, can_freeze, perish, conf, notes = (
                    "refrigerated",
                    2,
                    True,
                    "medium",
                    "low",
                    "assumed perishable",
                )

        output_rows.append(
            [
                title,
                description[:50] + "..." if len(description) > 50 else description,
                max_gap_days,
                storage,
                shelf_life,
                can_freeze,
                perish,
                conf,
                notes,
            ]
        )

with open(output_file, "w", encoding="utf-8", newline="") as f:
    writer = csv.writer(f)
    writer.writerows(output_rows)

print(f"Processed {len(output_rows) - 1} rows")
