# main.py
from pprint import pprint
from odds_api import load_player_odds
from predicted_stats import predict_stats_for_player
import yahoo_api
import requests


# Example usage of loading saved odds
# all_player_odds = load_player_odds()
# player_names = ["Joe Burrow", "Drake London", "Zach Charbonnet", "Sam LaPorta"]
# player_stats = {}
# for player_name in player_names:
#     if player_name in all_player_odds.keys():
#         player_stats[player_name] = predict_stats_for_player(all_player_odds[player_name])

# pprint(player_stats)

try: 
    rosters = yahoo_api.get_users_lineups()
          
except requests.exceptions.RequestException as e:
        print(f"ERROR when making API request: {e}")
        print(f"Response:")
        print(e.response.text)
        print(f"URL Requested: {e.request.url}")