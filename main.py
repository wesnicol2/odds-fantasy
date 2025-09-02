from pprint import pprint
from predicted_stats import predict_stats_for_player
import sleeper_api
import requests
import odds_api
from config import SLEEPER_ODDS_API_PLAYER_NAME_MAPPING, STAT_MARKET_MAPPING_SLEEPER

def calculate_fantasy_points(projected_stats, scoring_settings):
    """
    Calculate fantasy points for a player based on their projected stats and the league's scoring settings.

    Args:
        projected_stats (dict): A dictionary of the player's projected stats (e.g., passing yards, touchdowns).
        scoring_settings (dict): A dictionary of the league's scoring settings for different stat categories.

    Returns:
        float: The player's projected fantasy points.
    """
    fantasy_points = 0.0

    # Loop over each stat category in the projected stats
    for stat_key, stat_value in projected_stats.items():
        # Map the stat_key to the Yahoo stat_id using STAT_ID_MAPPING
        stat_id = STAT_MARKET_MAPPING_SLEEPER.get(stat_key)
        if not stat_id:
            continue  # If the stat_key isn't mapped, skip it

        # Find the corresponding stat_id in the league's scoring settings
        for stat, value in scoring_settings.items():
            if stat == stat_id:
                # Multiply the projected stat value by the league's scoring modifier
                modifier = float(value)
                fantasy_points += stat_value * modifier
                break  # Found the stat, no need to check further categories

    return fantasy_points


def print_rosters_with_projected_stats(username, season, use_saved_data=True):
    """
    Fetch and print the players along with their projected fantasy points and individual predicted stats in table format.
    Players are sorted by their predicted fantasy points in descending order.
    """
    try:
        roster = sleeper_api.get_user_sleeper_data(username, season)
        rosters = [roster] # TODO: In the future, enhance to get multiple rosters

        # Fetch odds for all games, either using saved data or fresh API data
        all_player_odds = odds_api.fetch_odds_for_all_games(rosters, use_saved_data=use_saved_data)
        
        # List to store player data for sorting later
        player_data_list = []
        all_stat_keys = set()  # To track all different stat keys

        # Loop through each roster
        for roster in rosters:

            # Get the league's scoring settings for the team
            league_settings = roster.get('scoring_rules')
            if not league_settings:
                continue

            # Loop through each player in the roster
            for player in roster["players"].values():
                # Use Odds API version of name from the beginning
                player_sleeper_name = player["name"]["full"]
                player_name = SLEEPER_ODDS_API_PLAYER_NAME_MAPPING.get(player_sleeper_name)
                if not player_name:
                    player_name = player_sleeper_name
                aggregated_player_odds = {}

                # Loop through all games' odds to find the player
                for game_id, game_odds in all_player_odds.items():
                    # Go through each bookmaker for the game
                    for bookmaker in game_odds["bookmakers"]:
                        bookmaker_key = bookmaker["key"]
                        # Check all markets for player odds
                        for market in bookmaker["markets"]:
                            for outcome in market["outcomes"]:
                                if "description" in outcome and outcome["description"] == player_name:
                                    if bookmaker_key not in aggregated_player_odds:
                                        aggregated_player_odds[bookmaker_key] = {}
                                    if market["key"] not in aggregated_player_odds[bookmaker_key]:
                                        aggregated_player_odds[bookmaker_key][market["key"]] = {
                                            "over": None,
                                            "under": None
                                        }

                                    # For simplicity, assume all odds are "Yes" (e.g., for anytime TD)
                                    # You can modify this logic to support "Over/Under" more explicitly
                                    aggregated_player_odds[bookmaker_key][market["key"]]["over"] = {
                                        "odds": outcome["price"],
                                        "point": outcome.get("point", 0)  # Use threshold if available, else 0
                                    }

                # If we found odds for the player, calculate projected stats and fantasy points
                if aggregated_player_odds:
                    projected_stats = predict_stats_for_player(aggregated_player_odds)
                    projected_fantasy_points = calculate_fantasy_points(projected_stats, league_settings)

                    # Track all unique stat keys for table columns
                    all_stat_keys.update(projected_stats.keys())

                    # Store player data in a list for sorting
                    player_data_list.append({
                        "player_name": player_name,
                        "projected_points": projected_fantasy_points,
                        "projected_stats": projected_stats  # Add predicted stats to player data
                    })
                else:
                    # If no odds data, treat player as 0 projected points
                    player_data_list.append({
                        "player_name": player_name,
                        "projected_points": 0.0,
                        "projected_stats": {}  # No stats available
                    })

        # Sort the players by projected fantasy points (descending order)
        sorted_player_data = sorted(player_data_list, key=lambda x: x["projected_points"], reverse=True)

        # Convert all_stat_keys to a sorted list for table columns
        all_stat_keys = sorted(all_stat_keys)

        # Print the table header with dynamic columns for each stat
        header = f"{'Player Name':<20} | {'Fantasy Points':>15} | " + " | ".join([f"{stat:<20}" for stat in all_stat_keys])
        print(header)
        print("-" * len(header))

        # Print each player's data in table format
        for player_data in sorted_player_data:
            player_name = player_data['player_name']
            projected_points = player_data['projected_points']
            predicted_stats = player_data['projected_stats']

            # Prepare the row with player name, fantasy points, and predicted stats
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
    
    Args:
        all_player_odds (dict): Dictionary containing odds data for all games and markets.
    
    Returns:
        list: List of betting opportunities where FanDuel has better odds and thresholds compared 
        to the average odds and thresholds from other sportsbooks.
    """
    opportunities = []

    # Iterate over all games and bookmakers
    for game_id, game_odds in all_player_odds.items():
        fanduel_odds = None

        # First, find FanDuel's odds for this game
        for bookmaker in game_odds["bookmakers"]:
            if bookmaker["key"] == "fanduel":
                fanduel_odds = bookmaker["markets"]  # Get all markets for FanDuel
                break

        if not fanduel_odds:
            continue  # Skip this game if FanDuel is not available

        # Compare FanDuel odds with the average odds and thresholds from other bookmakers
        for fanduel_market in fanduel_odds:
            fanduel_market_key = fanduel_market["key"]
            fanduel_outcomes = fanduel_market["outcomes"]

            # Track total odds, thresholds, and count for each outcome to calculate the average
            average_data = {}

            # Collect odds from all other bookmakers
            for bookmaker in game_odds["bookmakers"]:
                if bookmaker["key"] == "fanduel":
                    continue  # Skip FanDuel for averaging

                for market in bookmaker["markets"]:
                    if market["key"] == fanduel_market_key:
                        for outcome in market["outcomes"]:
                            player_name = outcome["description"]
                            price = outcome["price"]
                            threshold = outcome.get("point", 0)

                            

                            # Initialize if not present
                            if player_name not in average_data:
                                average_data[player_name] = {
                                    "total_price": 0,
                                    "total_threshold": 0,
                                    "count": 0
                                }

                            # Add up odds and thresholds
                            average_data[player_name]["total_price"] += price
                            average_data[player_name]["total_threshold"] += threshold
                            average_data[player_name]["count"] += 1
                            if player_name == "Trayveon Williams":
                                print("breakpoint")

            # Now compare FanDuel's odds with the average odds and thresholds
            for fanduel_outcome in fanduel_outcomes:
                fanduel_player = fanduel_outcome["description"]
                fanduel_price = fanduel_outcome["price"]
                fanduel_threshold = fanduel_outcome.get("point", 0)

                # If we have average data for this player and market
                if fanduel_player in average_data:
                    avg_data = average_data[fanduel_player]
                    if avg_data["count"] > 0:
                        avg_price = avg_data["total_price"] / avg_data["count"]
                        avg_threshold = avg_data["total_threshold"] / avg_data["count"]

                        # Compare FanDuel's odds and threshold with the average
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

    # Sort the opportunities by the biggest odds difference, then by threshold difference (both descending)
    sorted_opportunities = sorted(opportunities, key=lambda x: (x["odds_factor"], x["threshold_diff"]), reverse=True)

    return sorted_opportunities


def print_betting_opportunities(opportunities):
    """
    Prints a list of betting opportunities where FanDuel has better odds and thresholds compared to other sportsbooks.

    Args:
        opportunities (list): The list of opportunities sorted by odds and threshold advantage for FanDuel.
    """
    print(f"{'Player':<20} | {'Market':<20} | {'FD Odds':<10} | {'FD Threshold':<15} | {'Avg Odds':<10} | {'Avg Threshold':<15} | {'Odds Factor':<10} | {'Thresh Diff':<12}")
    print("-" * 110)
    
    for opp in opportunities:

        print(f"{opp['player']:<20} | {opp['market']:<20} | {opp['fanduel_odds']:<10} | {opp['fanduel_threshold']:<15} | {round(opp['average_odds'], 2):<10} | {round(opp['average_threshold'], 2):<15} | {round(opp['odds_factor'], 2):<10} | {round(opp['threshold_diff'], 2):<12}")

def print_defense_possiblities(username, season, use_saved_data=True):
    """
    Fetch and print possible defenses for the user's roster.
    """
    try:
        # Get all rosters from Sleeper
        roster = sleeper_api.get_user_sleeper_data(username, season)
        rosters = [roster] # TODO: In the future, enhance to get multiple rosters
        possible_defenses = set()

        # Loop through each roster
        for roster in rosters:
            # Get all avaliable defenses for each roster: 
            defenses = sleeper_api.get_available_defenses(roster)


            # Loop through each player in the roster
            for defense in defenses.values():
                print("TODO: Implement fetching defense stats and projected points")
                

        print("Possible Defenses in Your Roster:")
        for defense in possible_defenses:
            # Things to print for each defense: Team name, opposing team name, oposing team implied total, projected fantasy points
            print(f"  - {defense}")

    except requests.exceptions.RequestException as e:
        print(f"ERROR when making API request: {e}")
        print(f"Response: {e.response.text}")
        print(f"URL Requested: {e.request.url}")



if __name__ == "__main__":
    # Set `use_saved_data=False` to force fetching fresh odds data
    print_rosters_with_projected_stats(username="wesnicol", season="2025", use_saved_data=True)

    # print_defense_possiblities(username="wesnicol", season="2025", use_saved_data=True)
    
    
    # Assuming 'all_player_odds' contains the odds data for all games and markets
    # all_player_odds = odds_api.fetch_odds_for_all_games(rosters=None, use_saved_data=False)
    
    # # Find the betting opportunities where FanDuel offers better odds and thresholds
    # fanduel_opportunities = find_betting_opportunities_with_fanduel(all_player_odds)
    
    # # Print the betting opportunities
    # print_betting_opportunities(fanduel_opportunities)

