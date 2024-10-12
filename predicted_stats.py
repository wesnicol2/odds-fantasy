import json
# predicted_stats.py

# Mapping of stat_key (from odds data) to Yahoo stat_id
STAT_ID_MAPPING = {
    "player_pass_yds": 4,       # Passing Yards
    "player_pass_tds": 5,       # Passing Touchdowns
    "player_interceptions": 6,  # Interceptions
    "player_rush_yds": 9,       # Rushing Yards
    "player_rush_tds": 10,      # Rushing Touchdowns
    "player_reception_yds": 12, # Receiving Yards
    "player_reception_tds": 13, # Receiving Touchdowns
    "player_fumbles": 18,       # Fumbles Lost
    "player_anytime_td": 10     # 10 = rushing TDs, 13 = receiving TDs
}


def implied_probability(decimal_odds):
    """
    Convert decimal odds to implied probability.
    
    Args:
        decimal_odds (float): Decimal odds (e.g., 1.80).
    
    Returns:
        float: The implied probability as a decimal (e.g., 0.555 for 55.5%).
    """
    return 1 / decimal_odds


import math

def calculate_weighted_stat(over_prob, under_prob, threshold):
    """
    Predict the expected stat using adjusted over and under probabilities 
    and the bookmaker's threshold. Accounts for the vig (rake) by normalizing probabilities.
    
    Args:
        over_prob (float): The probability of the player exceeding the threshold.
        under_prob (float): The probability of the player falling short of the threshold.
        threshold (float): The bookmaker's threshold (e.g., 1.5 passing touchdowns).
    
    Returns:
        float: The predicted stat based on normalized probabilities and threshold.
    """

    # If we don't have under probability, assume it's 50%
    if under_prob == 0:
        under_prob = 0.5
    # Normalize the probabilities to account for the vig (make them sum to 1)
    
    total_prob = over_prob + under_prob
    if total_prob > 0:  # Avoid division by zero
        over_prob_normalized = over_prob / total_prob
        under_prob_normalized = under_prob / total_prob
    else:
        # If there's a problem with the odds, fallback to using 50/50
        over_prob_normalized = 0.5
        under_prob_normalized = 0.5
    
    # Difference between normalized over and under probabilities
    prob_diff = over_prob_normalized - under_prob_normalized
    
    # Scaling factor - we take a small proportion of the threshold to scale the shift
    scaling_factor = 0.5  # Tuning factor based on desired sensitivity
    
    # Calculate the predicted stat by shifting the threshold based on probability skew
    if threshold == 0: # Account for anytime touchdown special case
        predicted_stat = over_prob_normalized
    else:
        predicted_stat = threshold + prob_diff * scaling_factor * threshold
    
    return predicted_stat




def predict_stats_for_player(player_odds):
    """
    Predict stats for a player across all markets (e.g., passing yards, rushing yards) by averaging odds from all bookmakers.
    
    Args:
        player_odds (dict): Dictionary of a player's odds data across multiple bookmakers and markets.
    
    Returns:
        dict: Predicted stats for the player in each market, averaged across bookmakers.
    """
    predicted_stats = {}

    # Iterate over all bookmakers and markets for the player
    for bookmaker, markets in player_odds.items():
        for market_key, market_data in markets.items():
            over_data = market_data['over']
            under_data = market_data.get('under')

            # Initialize stats if this market hasn't been processed yet
            if market_key not in predicted_stats:
                predicted_stats[market_key] = {
                    "total_over_prob": 0,
                    "total_under_prob": 0,
                    "total_threshold": 0,
                    "bookmaker_count": 0
                }

            if over_data:
                over_odds = over_data['odds']
                threshold = over_data['point']
                over_prob = implied_probability(over_odds)

                # Aggregate the probabilities and thresholds
                predicted_stats[market_key]["total_over_prob"] += over_prob
                predicted_stats[market_key]["total_threshold"] += threshold

            if under_data:
                under_odds = under_data['odds']
                under_prob = implied_probability(under_odds)

                predicted_stats[market_key]["total_under_prob"] += under_prob

            # Count how many bookmakers are offering data for this market
            predicted_stats[market_key]["bookmaker_count"] += 1

    final_predicted_stats = {}

    # Calculate average probabilities and thresholds for each market
    for market_key, market_data in predicted_stats.items():
        bookmaker_count = market_data["bookmaker_count"]
        if bookmaker_count > 0:
            avg_over_prob = market_data["total_over_prob"] / bookmaker_count
            avg_under_prob = market_data["total_under_prob"] / bookmaker_count
            avg_threshold = market_data["total_threshold"] / bookmaker_count

            # Calculate predicted stats using the new formula
            final_predicted_stats[market_key] = calculate_weighted_stat(avg_over_prob, avg_under_prob, avg_threshold)

    return final_predicted_stats




def predict_stats_for_all_players(all_player_odds):
    """
    Predict stats for all players using their betting odds data by averaging data across all bookmakers.
    
    Args:
        all_player_odds (dict): Dictionary containing odds data for all players.
    
    Returns:
        dict: Predicted stats for all players across all markets.
    """
    all_predicted_stats = {}

    for player_name, player_odds in all_player_odds.items():
        predicted_stats = predict_stats_for_player(player_odds)
        if predicted_stats:
            all_predicted_stats[player_name] = predicted_stats

    return all_predicted_stats
