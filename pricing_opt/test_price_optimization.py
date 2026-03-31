import numpy as np
from price_optimization import get_item_elasticity, simulate_price_scenarios, suggest_new_price

# ==========================================
# TEST CASE 1: empirical elasticity
# ==========================================

tc1_category = "main"
tc1_price_history = [100.0, 70.0, 60.0, 110.0] 
tc1_quantity_history = [100, 100, 100, 100]
tc1_current_price = 200.0
tc1_current_cost = 190.0
tc1_current_quantity = 89

print("--- TEST CASE 1: Rule-Based (Constant History) ---")
result_1 = suggest_new_price(
    category=tc1_category,
    price_history=tc1_price_history,
    quantity_history=tc1_quantity_history,
    current_price=tc1_current_price,
    current_cost=tc1_current_cost,
    current_quantity=tc1_current_quantity
)
print(f"Estimation Method: {result_1['estimationMethod']}")
print(f"Elasticity: {result_1['elasticityEstimate']}")
print(f"Suggested Price: {result_1['suggestedPrice']} DKK")
print(f"Scenario Margins: {result_1['scenarioMargins']}\n")


# ==========================================
# TEST CASE 2: default elasiticity 
# ==========================================


tc2_category = "main"
tc2_price_history = [ 100.0]
tc2_quantity_history = [ 100]
tc2_current_price = 40.0
tc2_current_cost = 30.0
tc2_current_quantity = 89

print("--- TEST CASE 2: Empirical (Inelastic History) ---")
result_2 = suggest_new_price(
    category=tc2_category,
    price_history=tc2_price_history,
    quantity_history=tc2_quantity_history,
    current_price=tc2_current_price,
    current_cost=tc2_current_cost,
    current_quantity=tc2_current_quantity
)
print(f"Estimation Method: {result_2['estimationMethod']}")
print(f"Elasticity: {result_2['elasticityEstimate']}")
print(f"Suggested Price: {result_2['suggestedPrice']} DKK")
print(f"Scenario Margins: {result_2['scenarioMargins']}")