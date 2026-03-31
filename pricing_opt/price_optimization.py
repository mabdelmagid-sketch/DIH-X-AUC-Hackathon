import numpy as np

CATEGORY_DEFAULTS = {
    "beverage": -0.8,
    "main": -1.2,
    "dessert": -0.6,
    "addon": -0.5,
    "default": -1.0
}

def get_item_elasticity(category: str, price_history: list, quantity_history: list) -> dict:
    """
    Inputs:
        category: Item type string for default elasticity
        price_history: List of historical prices (DKK).
        quantity_history: List of units sold at corresponding prices.
    
    Outputs:
        Dictionary containing elasticityEstimate (float) and estimationMethod (string).
    """
    
    # Identify unique prices to determine if we can use empirical data
    unique_prices = np.unique(price_history)
    
    # Logic Rule: Use empirical if 2 or more different historical prices exist
    if len(unique_prices) >= 2:
        # Standard Log-Log Regression: ln(Q) = alpha + beta * ln(P)
        # The slope (beta) is our elasticity
        log_p = np.log(price_history)
        log_q = np.log(quantity_history)
        
        slope, _ = np.polyfit(log_p, log_q, 1)
        
        return {
            "elasticityEstimate": round(float(slope), 2),
            "estimationMethod": "empirical" #
        }
    
    # Fallback: Apply category defaults if insufficient price history
    default_val = CATEGORY_DEFAULTS.get(category.lower(), CATEGORY_DEFAULTS["default"])
    
    return {
        "elasticityEstimate": default_val,
        "estimationMethod": "rule_based" 
    }

def simulate_price_scenarios(current_price: float, current_cost: float, current_quantity: float, elasticity: float) -> dict:
    """
    Inputs:
        current_price: The current price of the item (DKK).
        current_cost: The cost of the item (DKK). Can be None if cost is not available.
        current_quantity: The current baseline units sold (for a given period).
        elasticity: The elasticity estimate (float) calculated previously.
        
    Outputs:
        Dictionary mapping the scenario adjustment (float) to its projected margin delta (float or None).
    """
    
    adjustments = [0.05, 0.10, 0.15, -0.05, -0.10, -0.15]
    
    scenario_margins = {}
    cost_available = current_cost is not None and current_cost > 0
    
    # Calculate baselines
    base_margin = (current_price - current_cost) * current_quantity if cost_available else 0.0
    
    for adj in adjustments:
        # Calculate new price
        new_price = current_price * (1 + adj)
        
        # Assertion: suggestedPrice must be > 0 and <= 10x current price
        if new_price <= 0 or new_price > (current_price * 10):
            continue
            
        # Calculate new quantity based on elasticity: % Change in Q = Elasticity * % Change in P
        delta_q_pct = elasticity * adj
        new_quantity = max(0.0, current_quantity * (1 + delta_q_pct)) # Prevent negative volume
        
        projected_margin_delta = None
        if cost_available:
            new_margin = (new_price - current_cost) * new_quantity
            projected_margin_delta = round(float(new_margin - base_margin), 2)
            
        # Map the adjustment percentage to its margin delta
        scenario_margins[float(adj)] = projected_margin_delta
        
    return scenario_margins

def suggest_new_price(category: str, price_history: list, quantity_history: list, current_price: float, current_cost: float, current_quantity: float) -> dict:
    """
    Orchestrator function that calculates elasticity, runs scenarios, 
    and suggests the price that yields the highest projected margin delta.
    """
    
    # Step 1: Calculate Elasticity
    elasticity_data = get_item_elasticity(category, price_history, quantity_history)
    elasticity_estimate = elasticity_data["elasticityEstimate"]
    estimation_method = elasticity_data["estimationMethod"]
    
    # Step 2: Run Simulations
    scenario_margins = simulate_price_scenarios(
        current_price=current_price, 
        current_cost=current_cost, 
        current_quantity=current_quantity, 
        elasticity=elasticity_estimate
    )
    
    # Step 3: Dynamically find the best price based on highest margin delta
    best_price = current_price
    best_margin_delta = 0.0 # Baseline: we only change the price if the margin actually improves
    
    for adj, margin_delta in scenario_margins.items():
        if margin_delta is not None and margin_delta > best_margin_delta:
            best_margin_delta = margin_delta
            best_price = current_price * (1 + adj)
            
    return {
        "suggestedPrice": round(float(best_price), 2),
        "estimationMethod": estimation_method,
        "elasticityEstimate": elasticity_estimate,
        "scenarioMargins": scenario_margins 
    }