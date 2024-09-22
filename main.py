# main.py
from pprint import pprint
from odds_api import load_player_odds


# Example usage of loading saved odds
all_player_odds = load_player_odds()
player_names = ["Joe Burrow", "Drake London", "Zach Charbonnet", "Sam LaPorta"]

for player_name in player_names:
    if player_name in all_player_odds.keys():
        print(player_name + " Odds:")
        pprint(all_player_odds[player_name])
