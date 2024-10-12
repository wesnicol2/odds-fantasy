from pprint import pprint
from predicted_stats import predict_stats_for_player, STAT_ID_MAPPING
import yahoo_api
import requests
import odds_api
from config import YAHOO_ODDS_API_PLAYER_NAME_MAPPING

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
        stat_id = STAT_ID_MAPPING.get(stat_key)
        if not stat_id:
            continue  # If the stat_key isn't mapped, skip it

        # Find the corresponding stat_id in the league's scoring settings
        for category in scoring_settings["stats"]["stat"]:
            if int(category["stat_id"]) == stat_id:
                # Multiply the projected stat value by the league's scoring modifier
                modifier = float(category["value"])
                fantasy_points += stat_value * modifier
                break  # Found the stat, no need to check further categories

    return fantasy_points


def print_rosters_with_projected_stats(use_saved_data=True):
    """
    Fetch and print the players along with their projected fantasy points and individual predicted stats in table format.
    Players are sorted by their predicted fantasy points in descending order.
    """
    try:
        # Get all rosters from Yahoo
        rosters = yahoo_api.get_users_lineups()

        # Fetch odds for all games, either using saved data or fresh API data
        all_player_odds = odds_api.fetch_odds_for_all_games(rosters, use_saved_data=use_saved_data)
        
        # List to store player data for sorting later
        player_data_list = []
        all_stat_keys = set()  # To track all different stat keys

        # Loop through each roster
        for roster in rosters:
            team_key = roster["team_key"]

            # Get the league's scoring settings for the team
            league_settings = yahoo_api.get_league_scoring_settings(team_key)
            if not league_settings:
                continue

            # Loop through each player in the roster
            for player in roster["players"]["player"]:
                # Use Odds API version of name from the beginning
                player_yahoo_name = player["name"]["full"]
                player_name = YAHOO_ODDS_API_PLAYER_NAME_MAPPING.get(player_yahoo_name)
                if not player_name:
                    player_name = player_yahoo_name
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


if __name__ == "__main__":
    # Set `use_saved_data=False` to force fetching fresh odds data
    print_rosters_with_projected_stats(use_saved_data=True)
