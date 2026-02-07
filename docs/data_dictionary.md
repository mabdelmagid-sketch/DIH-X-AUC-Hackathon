# Data Dictionary

## Source Data: Fresh Flow Markets (Copenhagen, Denmark)

All data from the `Inventory.Management/Inventory Management/` directory.

---

### fct_orders.csv (~400K rows)
Individual orders placed at restaurants.

| Column | Type | Description |
|--------|------|-------------|
| id | int | Unique order ID |
| user_id | int | Staff/user who processed the order |
| created | int | UNIX timestamp - order creation time |
| updated | int | UNIX timestamp - last update time |
| cash_amount | float | Cash amount paid (DKK) |
| channel | str | Order channel (App, etc.) |
| demo_mode | int | 1 = demo order (should be filtered out) |
| discount_amount | float | Discount applied (DKK) |
| items_amount | float | Total items cost before discounts (DKK) |
| payment_method | str | Payment method used |
| place_id | int | FK to dim_places.id |
| status | str | Order status: Closed, Open, Cancelled, etc. |
| total_amount | float | Final total (DKK) |
| type | str | Takeaway, Eat-in, Delivery |
| vat_amount | float | VAT amount (DKK, 25% rate) |

---

### fct_order_items.csv (~2M rows)
Individual line items within orders - **primary demand signal**.

| Column | Type | Description |
|--------|------|-------------|
| id | int | Unique order item ID |
| title | str | Item name (denormalized from dim_items) |
| campaign_id | int | FK to campaign if item was part of promotion |
| cost | float | Total cost (price * quantity) in DKK |
| discount_amount | float | Discount on this line item (DKK) |
| item_id | int | FK to dim_items.id |
| order_id | int | FK to fct_orders.id |
| price | float | Unit price (DKK) |
| quantity | int | Number of units ordered |
| status | str | Item status (Pending, etc.) |

---

### dim_items.csv (~89K rows)
Product/menu item catalog.

| Column | Type | Description |
|--------|------|-------------|
| id | int | Unique item ID |
| title | str | Item name |
| description | str | Item description |
| price | float | Standard price (DKK) |
| status | str | Active, Inactive, Deleted |
| type | str | Normal, Variable Price |
| section_id | int | Menu section FK |
| vat | float | VAT percentage |
| deleted | int | 1 = soft deleted |
| demo_mode | int | 1 = demo item |

---

### dim_places.csv (~10 rows)
Restaurant/store locations.

| Column | Type | Description |
|--------|------|-------------|
| id | int | Unique place ID |
| title | str | Store name (Eden Jaxx, Green Love, Crazy Chicken, etc.) |
| country | str | Country code (DK) |
| currency | str | Currency (DKK) |
| timezone | str | Timezone (Europe/Copenhagen) |
| latitude | float | Geographic latitude |
| longitude | float | Geographic longitude |
| opening_hours | JSON | Opening hours per day of week |
| street_address | str | Street address |

---

### fct_campaigns.csv (641 rows)
Promotional campaigns run at stores.

| Column | Type | Description |
|--------|------|-------------|
| id | int | Campaign ID |
| title | str | Campaign name/description |
| discount | float | Discount percentage |
| start_date_time | int | UNIX timestamp - campaign start |
| end_date_time | int | UNIX timestamp - campaign end |
| place_id | int | FK to dim_places.id |
| type | str | Campaign type (Discount on specific menu items, 2 for 1, etc.) |
| status | str | Active, Inactive |
| item_ids | str | Pipe-separated item IDs targeted |

---

### most_ordered.csv (~95K rows)
Pre-aggregated most ordered items per store.

| Column | Type | Description |
|--------|------|-------------|
| place_id | int | Store ID |
| item_id | int | Item ID |
| item_name | str | Item name |
| order_count | int | Total times ordered |

---

### dim_skus.csv (4 rows)
Stock keeping units with low stock thresholds.

| Column | Type | Description |
|--------|------|-------------|
| id | int | SKU ID |
| item_id | int | FK to dim_items.id |
| title | str | SKU name |
| quantity | float | Current stock quantity |
| low_stock_threshold | float | Alert threshold |
| type | str | normal, composite |
| unit | str | pcs, kg |

---

### fct_inventory_reports.csv (EMPTY)
Inventory stock level reports. **Contains only headers - no data.**

---

### Other dimension tables

- **dim_campaigns.csv**: Campaign dimension (id, place_id, status, type)
- **dim_add_ons.csv**: Add-on items (id, category_id, price, title)
- **dim_bill_of_materials.csv**: Recipe/BOM data
- **dim_menu_items.csv**: Menu item definitions
- **dim_menu_item_add_ons.csv**: Menu item to add-on mappings
- **dim_stock_categories.csv**: Stock categories (Kolde Drikke, Grøntsager, Pizza)
- **dim_taxonomy_terms.csv**: Taxonomy (gender, age groups)
- **dim_users.csv**: System users
- **fct_bonus_codes.csv**: Bonus/voucher codes
- **fct_cash_balances.csv**: Cash register balances
- **fct_invoice_items.csv**: Invoice line items
