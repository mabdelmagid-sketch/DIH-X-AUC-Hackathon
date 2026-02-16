#!/usr/bin/env python3
"""
FlowPOS Demo Data Seeder
Seeds realistic demo data for hackathon presentation.
"""
import requests
import json
import uuid
import random
import os
from datetime import datetime, timedelta, timezone

# === CONFIG ===
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ucqqeuogbhyqmsabqyac.supabase.co")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# Demo user auth IDs (from Supabase Auth)
ADMIN_AUTH_ID = "6ede2bb7-26a9-4a55-9546-c934bcae8ba7"
USER_AUTH_ID = "1b1202e8-d2e8-4209-b858-b20e97676b8b"


def api(token_unused, method, table, data=None, params=None):
    """Make Supabase REST API call using service role key (bypasses RLS)."""
    headers = {
        "apikey": SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())

    if method == "POST":
        resp = requests.post(url, headers=headers, json=data)
    elif method == "PATCH":
        resp = requests.patch(url, headers=headers, json=data)
    elif method == "GET":
        resp = requests.get(url, headers=headers)
    elif method == "DELETE":
        resp = requests.delete(url, headers=headers)
    else:
        raise ValueError(f"Unknown method: {method}")

    if resp.status_code >= 400:
        print(f"  ERROR {resp.status_code}: {resp.text[:200]}")
        return None
    try:
        return resp.json()
    except Exception:
        return resp.text


def uid():
    return str(uuid.uuid4())


def main():
    print("=== FlowPOS Demo Data Seeder ===\n")
    token = None  # Using service role key directly
    print("Using service role key (bypasses RLS).\n")

    now = datetime.now(timezone.utc)

    # === 1. CREATE ORGANIZATION ===
    print("1. Creating organization...")
    org_id = uid()
    org = api(token, "POST", "organizations", {
        "id": org_id,
        "name": "Fresh Flow Markets",
        "slug": f"fresh-flow-{int(now.timestamp())}",
        "status": "ACTIVE",
    })
    if not org:
        print("  Failed to create org, trying to use existing...")
        # Find existing
        org = api(token, "GET", "organizations", params={"name": "eq.Fresh Flow Markets", "limit": "1"})
        if org and len(org) > 0:
            org_id = org[0]["id"]
            print(f"  Using existing org: {org_id}")
        else:
            print("  FATAL: Cannot create or find org")
            return
    else:
        org_id = org[0]["id"] if isinstance(org, list) else org["id"]
    print(f"  Org ID: {org_id}")

    # === 2. CREATE LOCATION ===
    print("2. Creating location...")
    loc_id = uid()
    loc = api(token, "POST", "locations", {
        "id": loc_id,
        "organization_id": org_id,
        "name": "Copenhagen Central",
        "address": "Vesterbrogade 44, 1620 Copenhagen, Denmark",
        "phone": "+45 33 15 12 34",
        "is_active": True,
    })
    if loc:
        loc_id = loc[0]["id"] if isinstance(loc, list) else loc["id"]
    print(f"  Location ID: {loc_id}")

    # === 3. CREATE ORG SETTINGS ===
    print("3. Creating organization settings...")
    api(token, "POST", "organization_settings", {
        "organization_id": org_id,
    })

    # === 4. CREATE USER RECORDS ===
    print("4. Creating user records for demo accounts...")
    admin_user_id = uid()
    user_user_id = uid()

    admin_user = api(token, "POST", "users", {
        "id": admin_user_id,
        "auth_id": ADMIN_AUTH_ID,
        "organization_id": org_id,
        "email": "admin@demo.com",
        "name": "Ahmad Hassan",
        "role": "OWNER",
        "is_active": True,
    })
    if admin_user:
        admin_user_id = admin_user[0]["id"] if isinstance(admin_user, list) else admin_user["id"]
    print(f"  Admin user ID: {admin_user_id}")

    demo_user = api(token, "POST", "users", {
        "id": user_user_id,
        "auth_id": USER_AUTH_ID,
        "organization_id": org_id,
        "email": "user@demo.com",
        "name": "Sara Jensen",
        "role": "MANAGER",
        "is_active": True,
    })
    if demo_user:
        user_user_id = demo_user[0]["id"] if isinstance(demo_user, list) else demo_user["id"]
    print(f"  Demo user ID: {user_user_id}")

    # Additional staff users (without auth accounts)
    staff_users = []
    staff_data = [
        ("Mads Eriksen", "mads@freshflow.dk", "STAFF"),
        ("Fatima Al-Rashid", "fatima@freshflow.dk", "STAFF"),
        ("Lars Andersen", "lars@freshflow.dk", "KITCHEN"),
    ]
    for name, email, role in staff_data:
        sid = uid()
        u = api(token, "POST", "users", {
            "id": sid,
            "auth_id": uid(),  # dummy auth_id
            "organization_id": org_id,
            "email": email,
            "name": name,
            "role": role,
            "is_active": True,
        })
        if u:
            sid = u[0]["id"] if isinstance(u, list) else u["id"]
        staff_users.append(sid)

    print(f"  Created {len(staff_data)} staff users")

    # === 5. CREATE EMPLOYEES ===
    print("5. Creating employee records...")
    all_user_ids = [admin_user_id, user_user_id] + staff_users
    employee_ids = []
    for uid_val in all_user_ids:
        eid = uid()
        emp = api(token, "POST", "employees", {
            "id": eid,
            "user_id": uid_val,
            "location_id": loc_id,
            "is_active": True,
            "hourly_rate": random.randint(15000, 28000),  # 150-280 DKK/hr in cents
        })
        if emp:
            eid = emp[0]["id"] if isinstance(emp, list) else emp["id"]
        employee_ids.append(eid)
    print(f"  Created {len(employee_ids)} employees")

    # === 6. CREATE CATEGORIES ===
    print("6. Creating categories...")
    categories = [
        ("Hot Beverages", "Kaffe, te, varm chokolade", "#8B4513"),
        ("Cold Beverages", "Juice, smoothies, iced drinks", "#1E90FF"),
        ("Sandwiches", "Freshly made sandwiches & wraps", "#228B22"),
        ("Salads", "Fresh salads & bowls", "#32CD32"),
        ("Pastries", "Freshly baked pastries & bread", "#DAA520"),
        ("Breakfast", "Morning specials & brunch", "#FF8C00"),
        ("Snacks", "Quick bites & sides", "#CD853F"),
        ("Desserts", "Cakes, cookies & treats", "#FF69B4"),
    ]
    cat_ids = {}
    for name, desc, color in categories:
        cid = uid()
        cat = api(token, "POST", "categories", {
            "id": cid,
            "organization_id": org_id,
            "name": name,
            "description": desc,
            "color": color,
            "is_active": True,
        })
        if cat:
            cid = cat[0]["id"] if isinstance(cat, list) else cat["id"]
        cat_ids[name] = cid
    print(f"  Created {len(cat_ids)} categories")

    # === 7. CREATE PRODUCTS ===
    print("7. Creating products...")
    products_data = [
        # Hot Beverages
        ("Flat White", "Hot Beverages", 3800, 1200, True),
        ("Cappuccino", "Hot Beverages", 3600, 1100, True),
        ("Americano", "Hot Beverages", 3200, 800, True),
        ("Chai Latte", "Hot Beverages", 4200, 1400, True),
        ("Green Tea", "Hot Beverages", 2800, 600, True),
        ("Hot Chocolate", "Hot Beverages", 4000, 1200, True),
        # Cold Beverages
        ("Fresh Orange Juice", "Cold Beverages", 4500, 2000, True),
        ("Green Smoothie", "Cold Beverages", 5200, 2200, True),
        ("Iced Latte", "Cold Beverages", 4200, 1300, True),
        ("Sparkling Water", "Cold Beverages", 1800, 500, True),
        ("Berry Blast Smoothie", "Cold Beverages", 5500, 2400, True),
        # Sandwiches
        ("Avocado & Egg Sandwich", "Sandwiches", 6500, 2800, True),
        ("Smoked Salmon Bagel", "Sandwiches", 7200, 3200, True),
        ("Turkey Club Wrap", "Sandwiches", 6800, 2600, True),
        ("Falafel Pita", "Sandwiches", 5800, 2200, True),
        ("Grilled Cheese", "Sandwiches", 5200, 1800, True),
        # Salads
        ("Caesar Salad", "Salads", 7500, 2800, True),
        ("Greek Salad", "Salads", 6800, 2400, True),
        ("Quinoa Bowl", "Salads", 7800, 3200, True),
        ("Thai Chicken Salad", "Salads", 8200, 3400, True),
        # Pastries
        ("Butter Croissant", "Pastries", 2800, 800, True),
        ("Pain au Chocolat", "Pastries", 3200, 1000, True),
        ("Cinnamon Roll", "Pastries", 3500, 1200, True),
        ("Sourdough Bread", "Pastries", 4200, 1400, True),
        ("Almond Croissant", "Pastries", 3800, 1200, True),
        # Breakfast
        ("Eggs Benedict", "Breakfast", 8500, 3200, True),
        ("Acai Bowl", "Breakfast", 7200, 2800, True),
        ("Granola & Yoghurt", "Breakfast", 5800, 2000, True),
        ("Full Danish Breakfast", "Breakfast", 9800, 4200, True),
        # Snacks
        ("Energy Bar", "Snacks", 2200, 800, True),
        ("Mixed Nuts", "Snacks", 3200, 1200, True),
        ("Hummus & Crackers", "Snacks", 3800, 1400, True),
        # Desserts
        ("Carrot Cake Slice", "Desserts", 4500, 1600, True),
        ("Chocolate Brownie", "Desserts", 3800, 1200, True),
        ("Fruit Tart", "Desserts", 5200, 2000, True),
    ]

    product_ids = {}
    product_prices = {}
    for name, cat_name, price, cost, track_inv in products_data:
        pid = uid()
        prod = api(token, "POST", "products", {
            "id": pid,
            "organization_id": org_id,
            "category_id": cat_ids.get(cat_name),
            "name": name,
            "price": price,
            "cost": cost,
            "track_inventory": track_inv,
            "is_active": True,
        })
        if prod:
            pid = prod[0]["id"] if isinstance(prod, list) else prod["id"]
        product_ids[name] = pid
        product_prices[name] = price
    print(f"  Created {len(product_ids)} products")

    # === 8. CREATE INVENTORY ===
    print("8. Creating inventory items...")
    inv_count = 0
    for name, pid in product_ids.items():
        qty = random.randint(5, 80)
        low = random.choice([5, 10, 15])
        api(token, "POST", "inventory_items", {
            "id": uid(),
            "product_id": pid,
            "location_id": loc_id,
            "quantity": qty,
            "low_stock": low,
        })
        inv_count += 1
    print(f"  Created {inv_count} inventory items")

    # === 9. CREATE CUSTOMERS ===
    print("9. Creating customers...")
    customers_data = [
        ("Emma Larsen", "emma@email.dk", "+45 20 11 22 33", 520, 38500, 12),
        ("Oliver Petersen", "oliver.p@gmail.com", "+45 30 44 55 66", 380, 29200, 9),
        ("Sofie Andersen", "sofie.a@outlook.dk", "+45 40 77 88 99", 920, 67800, 24),
        ("Noah Christensen", "noah.c@email.dk", "+45 50 11 33 55", 180, 12400, 5),
        ("Ida Rasmussen", "ida.r@gmail.com", "+45 60 22 44 66", 640, 45600, 18),
        ("William Hansen", "william.h@email.dk", "+45 70 33 55 77", 290, 21800, 8),
        ("Freja Nielsen", "freja.n@outlook.dk", "+45 80 44 66 88", 1050, 78200, 28),
        ("Oscar Thomsen", None, "+45 90 55 77 99", 150, 9800, 4),
        ("Alma Madsen", "alma.m@gmail.com", None, 420, 34200, 11),
        ("Lucas Olsen", "lucas.o@email.dk", "+45 25 66 88 00", 760, 56400, 20),
        ("Mathilde Berg", "mathilde@freshflow.dk", "+45 35 77 99 11", 1380, 102400, 35),
        ("Viktor Skov", None, "+45 45 88 00 22", 80, 5600, 2),
    ]
    customer_ids = []
    for name, email, phone, points, spent, visits in customers_data:
        cid = uid()
        cust = api(token, "POST", "customers", {
            "id": cid,
            "organization_id": org_id,
            "name": name,
            "email": email,
            "phone": phone,
            "loyalty_points": points,
            "total_spent": spent,
            "visit_count": visits,
        })
        if cust:
            cid = cust[0]["id"] if isinstance(cust, list) else cust["id"]
        customer_ids.append(cid)
    print(f"  Created {len(customer_ids)} customers")

    # === 10. CREATE TABLES (Floor Plan) ===
    print("10. Creating restaurant tables...")
    tables_data = [
        ("T1", 2, 50, 50, 80, 80, "SQUARE", "AVAILABLE"),
        ("T2", 2, 180, 50, 80, 80, "SQUARE", "OCCUPIED"),
        ("T3", 4, 310, 50, 120, 80, "RECTANGLE", "AVAILABLE"),
        ("T4", 4, 50, 200, 120, 80, "RECTANGLE", "OCCUPIED"),
        ("T5", 6, 220, 200, 140, 100, "RECTANGLE", "AVAILABLE"),
        ("T6", 2, 410, 50, 80, 80, "CIRCLE", "RESERVED"),
        ("T7", 4, 410, 200, 100, 100, "CIRCLE", "AVAILABLE"),
        ("T8", 8, 50, 370, 180, 100, "RECTANGLE", "AVAILABLE"),
        ("T9", 2, 300, 370, 80, 80, "SQUARE", "DIRTY"),
        ("T10", 4, 430, 370, 120, 80, "RECTANGLE", "AVAILABLE"),
        ("Bar 1", 1, 50, 520, 60, 60, "CIRCLE", "AVAILABLE"),
        ("Bar 2", 1, 130, 520, 60, 60, "CIRCLE", "OCCUPIED"),
    ]
    table_ids = []
    for name, cap, x, y, w, h, shape, status in tables_data:
        tid = uid()
        tbl = api(token, "POST", "tables", {
            "id": tid,
            "location_id": loc_id,
            "name": name,
            "capacity": cap,
            "pos_x": x,
            "pos_y": y,
            "width": w,
            "height": h,
            "shape": shape,
            "status": status,
        })
        if tbl:
            tid = tbl[0]["id"] if isinstance(tbl, list) else tbl["id"]
        table_ids.append(tid)
    print(f"  Created {len(table_ids)} tables")

    # === 11. CREATE ORDERS ===
    print("11. Creating orders (recent + historical)...")
    product_names = list(product_ids.keys())
    order_types = ["DINE_IN", "DINE_IN", "DINE_IN", "TAKEOUT", "TAKEOUT", "DELIVERY"]
    order_statuses = ["COMPLETED", "COMPLETED", "COMPLETED", "COMPLETED", "COMPLETED",
                      "OPEN", "IN_PROGRESS", "READY"]

    order_count = 0
    # Create orders spread over last 7 days
    for day_offset in range(7, -1, -1):
        day = now - timedelta(days=day_offset)
        # More orders on recent days, fewer on old
        num_orders = random.randint(8, 18) if day_offset <= 2 else random.randint(4, 10)

        for i in range(num_orders):
            order_id = uid()
            order_num = order_count + 1

            # Random time during business hours (7am - 9pm)
            hour = random.randint(7, 21)
            minute = random.randint(0, 59)
            order_time = day.replace(hour=hour, minute=minute, second=random.randint(0, 59))

            # Pick status based on day
            if day_offset == 0:
                status = random.choice(order_statuses)
            else:
                status = "COMPLETED"

            order_type = random.choice(order_types)

            # Pick 1-4 random items
            num_items = random.randint(1, 4)
            selected_items = random.sample(product_names, min(num_items, len(product_names)))

            # Build order items
            order_items_data = []
            subtotal = 0
            for item_name in selected_items:
                qty = random.randint(1, 3)
                unit_price = product_prices[item_name]
                total_price = unit_price * qty
                subtotal += total_price
                order_items_data.append({
                    "id": uid(),
                    "order_id": order_id,
                    "product_id": product_ids[item_name],
                    "name": item_name,
                    "quantity": qty,
                    "unit_price": unit_price,
                    "total_price": total_price,
                    "status": "DELIVERED" if status == "COMPLETED" else "PENDING",
                })

            tax_amount = int(subtotal * 0.25)  # Danish VAT 25%
            total = subtotal + tax_amount
            tip = random.choice([0, 0, 0, 0, 500, 1000, 1500, 2000])

            # Create order
            order_data = {
                "id": order_id,
                "order_number": order_num,
                "organization_id": org_id,
                "location_id": loc_id,
                "employee_id": random.choice(employee_ids) if employee_ids else None,
                "type": order_type,
                "status": status,
                "subtotal": subtotal,
                "tax_amount": tax_amount,
                "discount_amount": 0,
                "tip_amount": tip,
                "total": total + tip,
                "created_at": order_time.isoformat(),
                "updated_at": order_time.isoformat(),
            }
            if status == "COMPLETED":
                order_data["completed_at"] = (order_time + timedelta(minutes=random.randint(10, 45))).isoformat()

            # Assign customer to ~40% of orders
            if random.random() < 0.4 and customer_ids:
                order_data["customer_id"] = random.choice(customer_ids)

            # Assign table to dine-in orders
            if order_type == "DINE_IN" and table_ids:
                order_data["table_id"] = random.choice(table_ids)

            result = api(token, "POST", "orders", order_data)
            if result:
                # Create order items
                for item_data in order_items_data:
                    api(token, "POST", "order_items", item_data)
                order_count += 1

    print(f"  Created {order_count} orders with items")

    # === SUMMARY ===
    print(f"""
=== SEEDING COMPLETE ===
Organization: Fresh Flow Markets ({org_id})
Location:     Copenhagen Central ({loc_id})
Users:        {2 + len(staff_data)} (admin@demo.com = Owner, user@demo.com = Manager)
Categories:   {len(cat_ids)}
Products:     {len(product_ids)}
Inventory:    {inv_count} items
Customers:    {len(customer_ids)}
Tables:       {len(table_ids)}
Orders:       {order_count}

Login with:
  admin@demo.com / admin123@   (Owner)
  user@demo.com  / demo123@    (Manager)

Frontend:  https://pos-frontend-production-56bb.up.railway.app
Dashboard: https://pos-frontend-production-56bb.up.railway.app/dashboard
""")


if __name__ == "__main__":
    main()
