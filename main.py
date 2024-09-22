# main.py
from pprint import pprint
from odds_api import load_player_odds
from predicted_stats import predict_stats_for_player


# Example usage of loading saved odds
all_player_odds = load_player_odds()
player_names = ["Joe Burrow", "Drake London", "Zach Charbonnet", "Sam LaPorta"]

for player_name in player_names:
    if player_name in all_player_odds.keys():
        print(player_name + " Projected Stats:")
        pprint(predict_stats_for_player(all_player_odds[player_name]))
