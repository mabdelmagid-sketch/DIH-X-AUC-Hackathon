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
