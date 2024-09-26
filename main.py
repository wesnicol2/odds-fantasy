from pprint import pprint
from predicted_stats import predict_stats_for_player, STAT_ID_MAPPING
import yahoo_api
import requests
import odds_api


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
    Fetch and print the players along with their projected fantasy points.
    Players are sorted by their predicted fantasy points in descending order.
    The output is simplified to just show player names and their projected points.
    """
    try:
        # Get all rosters from Yahoo
        rosters = yahoo_api.get_users_lineups()

        # Fetch odds for all games, either using saved data or fresh API data
        all_player_odds = odds_api.fetch_odds_for_all_games(rosters, use_saved_data=use_saved_data)
        
        # List to store player data for sorting later
        player_data_list = []

        # Loop through each roster
        for roster in rosters:
            team_key = roster["team_key"]

            # Get the league's scoring settings for the team
            league_settings = yahoo_api.get_league_scoring_settings(team_key)
            if not league_settings:
                continue

            # Loop through each player in the roster
            for player_name in roster["players"]:
                # Check if the player has odds data
                if player_name in all_player_odds.keys():
                    player_odds = all_player_odds[player_name]
                    
                    # Get the predicted stats for the player
                    projected_stats = predict_stats_for_player(player_odds)

                    # Calculate projected fantasy points
                    projected_fantasy_points = calculate_fantasy_points(projected_stats, league_settings)

                    # Store player data in a list for sorting
                    player_data_list.append({
                        "player_name": player_name,
                        "projected_points": projected_fantasy_points
                    })
                else:
                    # If no odds data, treat player as 0 projected points
                    player_data_list.append({
                        "player_name": player_name,
                        "projected_points": 0.0
                    })

        # Sort the players by projected fantasy points (descending order)
        sorted_player_data = sorted(player_data_list, key=lambda x: x["projected_points"], reverse=True)

        # Print the simplified output with just headers and values
        print(f"{'Player Name':<20} | {'Projected Points':>17}")
        print("-" * 40)
        for player_data in sorted_player_data:
            print(f"{player_data['player_name']:<20} | {player_data['projected_points']:>17.2f}")

    except requests.exceptions.RequestException as e:
        print(f"ERROR when making API request: {e}")
        print(f"Response: {e.response.text}")
        print(f"URL Requested: {e.request.url}")


if __name__ == "__main__":
    # Set `use_saved_data=False` to force fetching fresh odds data
    print_rosters_with_projected_stats(use_saved_data=False)
