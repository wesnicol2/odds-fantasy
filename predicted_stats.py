# predicted_stats.py

# Mapping of stat_key (from odds data) to Yahoo stat_id
STAT_ID_MAPPING = {
    "player_pass_yds": 4,      # Passing Yards
    "player_pass_tds": 5,      # Passing Touchdowns
    "player_interceptions": 6, # Interceptions
    "player_rush_yds": 9,      # Rushing Yards
    "player_rush_tds": 10,     # Rushing Touchdowns
    "player_reception_yds": 12,# Receiving Yards
    "player_reception_tds": 13,# Receiving Touchdowns
    "player_fumbles": 18       # Fumbles Lost
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


def calculate_weighted_stat(over_prob, under_prob, threshold):
    """
    Calculate the predicted stat using a weighted average based on implied probabilities.
    
    Args:
        over_prob (float): The implied probability for the "Over" outcome.
        under_prob (float): The implied probability for the "Under" outcome.
        threshold (float): The betting threshold (e.g., passing yards over/under).
    
    Returns:
        float: The predicted stat (e.g., predicted passing yards).
    """
    return (over_prob * threshold) + (under_prob * threshold)


def predict_stats_for_player(player_odds):
    """
    Predict stats for a player across all markets (e.g., passing yards, rushing yards) by averaging odds from all bookmakers.
    
    Args:
        player_odds (dict): Dictionary of a player's odds data across multiple bookmakers and markets.
    
    Returns:
        dict: Predicted stats for the player in each market, averaged across bookmakers.
    """
    predicted_stats = {}
    total_over_prob = 0
    total_under_prob = 0
    total_threshold = 0
    bookmaker_count = 0

    # Iterate over all bookmakers for the market
    stats = {}
    for bookmaker, markets in player_odds.items():
        for market_key, market_data in markets.items():
            over_data = market_data['over']
            under_data = market_data['under']

            if over_data is None and under_data is None:
                continue; 
            elif over_data is None:
                over_data = under_data
            elif under_data is None:
                under_data = over_data

            # Extract odds and threshold from market data
            over_odds = over_data['odds']
            under_odds = under_data['odds']
            threshold = over_data['point']  # Assuming both over and under have the same threshold

            # Convert odds to probabilities
            over_prob = implied_probability(over_odds)
            under_prob = implied_probability(under_odds)

            if market_key not in stats.keys():
                stats[market_key] = {"total_over_prob": over_prob,
                                     "total_under_prob": under_prob,
                                     "total_threshold": threshold,
                                     "count": 1}
            else:
                stats[market_key]["total_over_prob"] += over_prob
                stats[market_key]["total_under_prob"] += under_prob
                stats[market_key]["total_threshold"] += threshold
                stats[market_key]["count"] += 1
                
    final_predicted_stats = {}
    # Average probabilities and threshold across bookmakers
    for market_key, totals in stats.items():
        avg_over_prob = totals["total_over_prob"] / totals["count"]
        avg_under_prob = totals["total_under_prob"] / totals["count"]
        avg_threshold = totals["total_threshold"] / totals["count"]
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
