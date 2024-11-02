from pprint import pprint
from predicted_stats import predict_stats_for_player, STAT_ID_MAPPING
import yahoo_api
import requests
import odds_api
from config import YAHOO_ODDS_API_PLAYER_NAME_MAPPING
import json

def calculate_bonus_points(stat_value, bonus_details):
    # TODO: Improve this so that it uses odds specific to the thresholds rather than statistical analysis
    proximity_precentage = 20 # This is the threshold to start considering bonus points. A value of 10 means if a player is predicted to get within 10% of their threshold for a specific bonus, they'll start getting bonus points based on the formula below
    proximity_decimal = proximity_precentage / 100
    inverse_proximity_decimal = 1 - proximity_decimal
    
    total_bonus_points = 0.0
    for bonus in bonus_details:
        target = float(bonus['target'])
        points = float(bonus['points'])
        

        # Check if stat_value is within the proximity percentage of the target for partial points
        lower_threshold = target * inverse_proximity_decimal
        upper_threshold = target + target * proximity_decimal
        if stat_value >= lower_threshold:
            if stat_value >= upper_threshold:
                # If stat value is far enough above the target, just apply all bonus points
                bonus_points = points
            else:
                # Calculate a fraction of the bonus based on proximity to the target
                bonus_points = ( points / ( 2 * (target - lower_threshold)) ) * (stat_value - target) + ( points / 2 )
            total_bonus_points += bonus_points

    return total_bonus_points

def calculate_fantasy_points(projected_stats, scoring_settings):
    """
    Calculate fantasy points for a player based on their projected stats and the league's scoring settings.
    """
    fantasy_points = 0.0
    for stat_key, stat_value in projected_stats.items():
        stat_id = STAT_ID_MAPPING.get(stat_key)
        if not stat_id:
            continue
        for category in scoring_settings["stats"]["stat"]:
            if int(category["stat_id"]) == stat_id:
                modifier = float(category["value"])
                bonus_points = 0.0
                if category.get('bonuses'):
                    bonus_points = calculate_bonus_points(stat_value, category['bonuses']['bonus'])
                fantasy_points += stat_value * modifier + bonus_points
                break
    return fantasy_points


def predict_stat_from_odds(over_odds, under_odds, threshold):
    """
    Placeholder function to calculate predicted stat based on odds and threshold.
    Actual implementation will be added later.
    """
    # Placeholder logic - actual logic to be implemented later
    return (over_odds + under_odds) / 2 * threshold  # Simplified example, not real calculation


def aggregate_player_odds(player_name, all_player_odds):
    aggregated_odds = {}
    # Loop through each game and bookmaker in all_player_odds
    for game_id, game_data in all_player_odds.items():
        for bookmaker in game_data["bookmakers"]:
            bookmaker_key = bookmaker["key"]
            for market in bookmaker["markets"]:
                market_key = market["key"]
                
                
                # Find outcomes for the specified player in this market
                outcomes = [outcome for outcome in market["outcomes"] if outcome.get("description") == player_name]
                
                
                if outcomes:
                    # Identify Over and Under outcomes, if available
                    over_odds, under_odds, threshold = None, None, None
                    for outcome in outcomes:
                        if outcome["name"].lower() == "over":
                            over_odds = outcome["price"]
                            threshold = outcome["point"]
                        elif outcome["name"].lower() == "under":
                            under_odds = outcome["price"]
                            threshold = outcome["point"]
                        elif outcome["name"] == "Yes":
                            # TODO: Improve this so that it uses anytime td alternate odds also
                            # TODO: Improve logic from just looking for anytime td to looking for all non-threshld odds
                            over_odds = outcome["price"]
                            under_odds = None
                            threshold = 1

                    # Initialize the market key if not present
                    if market_key not in aggregated_odds:
                        aggregated_odds[market_key] = {}
                    # Use the bookmaker_key instead of the full dictionary as the key
                    if bookmaker_key not in aggregated_odds[market_key]:
                        aggregated_odds[market_key][bookmaker_key] = {}
                    aggregated_odds[market_key][bookmaker_key] = {
                        "over_odds": over_odds,
                        "under_odds": under_odds,
                        "threshold": threshold
                    }

    return aggregated_odds


def predict_stats_from_odds(player, all_player_odds):
    """
    Predict stats for a player across all markets using the odds data.

    Args:
        player (dict): Player dictionary with details like name and position.
        all_player_odds (dict): Odds data for all games and players from various bookmakers.

    Returns:
        dict: Predicted stats for each market/stat relevant to the player.
    """
    player_name = YAHOO_ODDS_API_PLAYER_NAME_MAPPING.get(player["name"]["full"], player["name"]["full"])
    predicted_stats = {}
    aggregated_player_odds = aggregate_player_odds(player_name, all_player_odds)
    aggregated_player_stat_probabilities=derive_probabilities_from_aggregated_odds(aggregated_player_odds)
    predicted_stats = combine_probabilities_from_bookmakers(aggregated_player_stat_probabilities)
    
    return predicted_stats


def implied_probability(odds):
    """Calculate implied probability from decimal odds."""
    if odds is None:
        return None
    else:
        return 1 / odds

def get_fair_probability_from_odds(over_odds, under_odds, threshold):
    """
    Calculate the fair probability of an event occurring (Over/Under) by adjusting for the bookmaker's vig.
    
    Args:
        over_odds (float): The odds for the "Over" outcome.
        under_odds (float): The odds for the "Under" outcome.
        threshold (float): The line or threshold set by the bookmaker (e.g., points, yards).
    
    Returns:
        dict: A dictionary containing the fair probabilities for "Over" and "Under".
    """
    # Step 1: Calculate implied probabilities from odds
    implied_over_prob = implied_probability(over_odds)
    implied_under_prob = implied_probability(under_odds)
    
    # Step 2: Adjust for the vig by normalizing
    total_implied_prob = implied_over_prob + implied_under_prob
    fair_over_prob = implied_over_prob / total_implied_prob
    fair_under_prob = implied_under_prob / total_implied_prob
    
    return {
        "over": fair_over_prob,
        "under": fair_under_prob,
        "threshold": threshold
    }



def derive_probabilities_from_aggregated_odds(aggregated_player_odds):
    aggregated_player_stat_probabilities = {}
    for market_key, market in aggregated_player_odds.items():
            for bookmaker_key, bookmaker in market.items():
                if bookmaker["over_odds"] is not None and bookmaker["threshold"] is not None:
                    if bookmaker["under_odds"] is None:
                        # Handle cases of binary odds like anytime TD
                        # TODO: Currently we assume no vig, how could we improve that?
                        bookmaker["under_odds"] = 1 / (1 - implied_probability(bookmaker["over_odds"]))
                    # Initialize the market key if not present
                    if market_key not in aggregated_player_stat_probabilities:
                        aggregated_player_stat_probabilities[market_key] = {}
                    # Use the bookmaker_key instead of the full dictionary as the key
                    if bookmaker_key not in aggregated_player_stat_probabilities[market_key]:
                        aggregated_player_stat_probabilities[market_key][bookmaker_key] = {}

                    aggregated_player_stat_probabilities[market_key][bookmaker_key] = get_fair_probability_from_odds(over_odds=bookmaker["over_odds"], under_odds=bookmaker["under_odds"], threshold=bookmaker["threshold"])

    return aggregated_player_stat_probabilities

def combine_probabilities_from_bookmakers(aggregated_player_stat_probabilities):
    """
    Combines probabilities from different bookmakers into a single predicted stat value for each market/stat
    by calculating a weighted average of thresholds based on probabilities.

    Args:
        aggregated_player_stat_probabilities (dict): Dictionary containing over/under probabilities 
                                                     and thresholds from various bookmakers.
                                                     
    Returns:
        dict: Combined predicted stat values for each market/stat.
    """
    combined_predictions = {}

    for stat, bookmakers_data in aggregated_player_stat_probabilities.items():
        weighted_threshold_sum = 0
        total_weight = 0

        # Calculate weighted threshold based on probabilities
        for bookmaker, odds_data in bookmakers_data.items():
            threshold = odds_data["threshold"]
            over_prob = odds_data["over"]

            # TODO: For anytime TD (and maybe others) we're getting 1 as the predicted stat - we need to somehow get this to use the under/over probability to predict - if there's 25% chance of going over 1 td, then we should write 0.25 touchdowns are predicted (this will be improved when we have odds for more TD possiblities such as odds to go over 2 TDs)
            # Use the probability of going over as a weight for this threshold
            weighted_threshold_sum += threshold * over_prob
            total_weight += over_prob

        # Compute the implied stat as a weighted average of thresholds
        if total_weight > 0:
            implied_stat_value = weighted_threshold_sum / total_weight
        else:
            implied_stat_value = sum([odds_data["threshold"] for odds_data in bookmakers_data.values()]) / len(bookmakers_data)

        # Store the predicted stat value for this market/stat
        combined_predictions[stat] = implied_stat_value

    return combined_predictions



def predict_fantasy_points_from_stats(player_predicted_stats, league_settings):
    print("predict_fantasy_points_from_stats not yet implemented")
    return None


def print_rosters_with_projected_stats(use_saved_data=True):
    """
    Fetch rosters and odds, process stats, and print players' projected fantasy points and stats.
    """
    try:
        rosters = yahoo_api.get_users_lineups()
        # TODO: Consider getting league scoring settings before fetching odds and only get the markets that will matter for scoring.
        # TODO: Try getting alternate markets, they might have some cool specific odds like odds to break 100 yards
        all_player_odds = odds_api.fetch_odds_for_all_games(rosters, use_saved_data=use_saved_data)
        player_data_list = []
        all_stat_keys = set()

        for roster in rosters:
            team_key = roster["team_key"]
            league_settings = yahoo_api.get_league_scoring_settings(team_key)
            if not league_settings:
                continue

            for player in roster["players"]["player"]:
                player["predicted_stats"] = predict_stats_from_odds(player=player, all_player_odds=all_player_odds)
                continue
                player["predicted_fantasy_points"] = predict_fantasy_points_from_stats(player_predicted_stats=player["predicted_stats"], league_settings=league_settings)
                all_stat_keys.update(player["predicted_fantasy_points"]["projected_stats"].keys())
                player_data_list.append(player_data)

        sorted_player_data = sorted(player_data_list, key=lambda x: x["projected_points"], reverse=True)
        all_stat_keys = sorted(all_stat_keys)

        header = f"{'Player Name':<20} | {'Fantasy Points':>15} | " + " | ".join([f"{stat:<20}" for stat in all_stat_keys])
        print(header)
        print("-" * len(header))

        for player_data in sorted_player_data:
            player_name = player_data['player_name']
            projected_points = player_data['projected_points']
            predicted_stats = player_data['projected_stats']
            row = f"{player_name:<20} | {projected_points:>15.2f} | "
            row += " | ".join([f"{predicted_stats.get(stat, 0):<20.2f}" for stat in all_stat_keys])
            print(row)

    except requests.exceptions.RequestException as e:
        print(f"ERROR when making API request: {e}")
        print(f"Response: {e.response.text}")
        print(f"URL Requested: {e.request.url}")


def find_betting_opportunities_with_fanduel(all_player_odds):
    """
    Identifies betting opportunities where FanDuel offers better odds and/or better thresholds 
    compared to the average odds and thresholds from other bookmakers for the same player and market. 
    Sorts by the largest advantage for FanDuel.
    """
    opportunities = []
    for game_id, game_odds in all_player_odds.items():
        fanduel_odds = None
        for bookmaker in game_odds["bookmakers"]:
            if bookmaker["key"] == "fanduel":
                fanduel_odds = bookmaker["markets"]
                break

        if not fanduel_odds:
            continue

        for fanduel_market in fanduel_odds:
            fanduel_market_key = fanduel_market["key"]
            fanduel_outcomes = fanduel_market["outcomes"]
            average_data = {}

            for bookmaker in game_odds["bookmakers"]:
                if bookmaker["key"] == "fanduel":
                    continue
                for market in bookmaker["markets"]:
                    if market["key"] == fanduel_market_key:
                        for outcome in market["outcomes"]:
                            player_name = outcome["description"]
                            price = outcome["price"]
                            threshold = outcome.get("point", 0)

                            if player_name not in average_data:
                                average_data[player_name] = {
                                    "total_price": 0,
                                    "total_threshold": 0,
                                    "count": 0
                                }

                            average_data[player_name]["total_price"] += price
                            average_data[player_name]["total_threshold"] += threshold
                            average_data[player_name]["count"] += 1

            for fanduel_outcome in fanduel_outcomes:
                fanduel_player = fanduel_outcome["description"]
                fanduel_price = fanduel_outcome["price"]
                fanduel_threshold = fanduel_outcome.get("point", 0)

                if fanduel_player in average_data:
                    avg_data = average_data[fanduel_player]
                    if avg_data["count"] > 0:
                        avg_price = avg_data["total_price"] / avg_data["count"]
                        avg_threshold = avg_data["total_threshold"] / avg_data["count"]
                        if fanduel_price > avg_price:
                            odds_factor = fanduel_price / avg_price
                            threshold_diff = fanduel_threshold - avg_threshold
                            opportunities.append({
                                "player": fanduel_player,
                                "market": fanduel_market_key,
                                "fanduel_odds": fanduel_price,
                                "fanduel_threshold": fanduel_threshold,
                                "average_odds": avg_price,
                                "average_threshold": avg_threshold,
                                "odds_factor": odds_factor,
                                "threshold_diff": threshold_diff,
                                "game_id": game_id
                            })

    sorted_opportunities = sorted(opportunities, key=lambda x: (x["odds_factor"], x["threshold_diff"]), reverse=True)
    return sorted_opportunities


def print_betting_opportunities(opportunities):
    """
    Prints a list of betting opportunities where FanDuel has better odds and thresholds compared to other sportsbooks.
    """
    print(f"{'Player':<20} | {'Market':<20} | {'FD Odds':<10} | {'FD Threshold':<15} | {'Avg Odds':<10} | {'Avg Threshold':<15} | {'Odds Factor':<10} | {'Thresh Diff':<12}")
    print("-" * 110)
    
    for opp in opportunities:
        print(f"{opp['player']:<20} | {opp['market']:<20} | {opp['fanduel_odds']:<10} | {opp['fanduel_threshold']:<15} | {round(opp['average_odds'], 2):<10} | {round(opp['average_threshold'], 2):<15} | {round(opp['odds_factor'], 2):<10} | {round(opp['threshold_diff'], 2):<12}")


if __name__ == "__main__":
    print_rosters_with_projected_stats(use_saved_data=True)
    # all_player_odds = odds_api.fetch_odds_for_all_games(rosters=None, use_saved_data=False)
    # fanduel_opportunities = find_betting_opportunities_with_fanduel(all_player_odds)
    # print_betting_opportunities(fanduel_opportunities)
