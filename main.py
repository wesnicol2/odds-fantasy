from pprint import pprint
from predicted_stats import predict_stats_for_player, STAT_ID_MAPPING
import yahoo_api
import requests
import odds_api
from config import YAHOO_ODDS_API_PLAYER_NAME_MAPPING

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


def fetch_rosters_and_odds(use_saved_data=True):
    """
    Fetch rosters from Yahoo and odds data for each player.
    """
    rosters = yahoo_api.get_users_lineups()
    all_player_odds = odds_api.fetch_odds_for_all_games(rosters, use_saved_data=use_saved_data)
    return rosters, all_player_odds


def process_player_stats(player, league_settings, all_player_odds):
    """
    Process the stats for a single player: calculate projected stats and fantasy points.
    """
    player_name = YAHOO_ODDS_API_PLAYER_NAME_MAPPING.get(player["name"]["full"], player["name"]["full"])
    aggregated_player_odds = {}

    for game_id, game_odds in all_player_odds.items():
        for bookmaker in game_odds["bookmakers"]:
            bookmaker_key = bookmaker["key"]
            for market in bookmaker["markets"]:
                for outcome in market["outcomes"]:
                    if "description" in outcome and outcome["description"] == player_name:
                        if bookmaker_key not in aggregated_player_odds:
                            aggregated_player_odds[bookmaker_key] = {}
                        if market["key"] not in aggregated_player_odds[bookmaker_key]:
                            aggregated_player_odds[bookmaker_key][market["key"]] = {"over": None, "under": None}
                        aggregated_player_odds[bookmaker_key][market["key"]]["over"] = {
                            "odds": outcome["price"],
                            "point": outcome.get("point", 0)
                        }

    if aggregated_player_odds:
        projected_stats = predict_stats_for_player(aggregated_player_odds)
        projected_fantasy_points = calculate_fantasy_points(projected_stats, league_settings)
        return {
            "player_name": player_name,
            "projected_points": projected_fantasy_points,
            "projected_stats": projected_stats
        }
    else:
        return {
            "player_name": player_name,
            "projected_points": 0.0,
            "projected_stats": {}
        }


def print_rosters_with_projected_stats(use_saved_data=True):
    """
    Fetch rosters and odds, process stats, and print players' projected fantasy points and stats.
    """
    try:
        rosters, all_player_odds = fetch_rosters_and_odds(use_saved_data=use_saved_data)
        player_data_list = []
        all_stat_keys = set()

        for roster in rosters:
            team_key = roster["team_key"]
            league_settings = yahoo_api.get_league_scoring_settings(team_key)
            if not league_settings:
                continue

            for player in roster["players"]["player"]:
                player_data = process_player_stats(player, league_settings, all_player_odds)
                all_stat_keys.update(player_data["projected_stats"].keys())
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
    print_rosters_with_projected_stats(use_saved_data=False)
    # all_player_odds = odds_api.fetch_odds_for_all_games(rosters=None, use_saved_data=False)
    # fanduel_opportunities = find_betting_opportunities_with_fanduel(all_player_odds)
    # print_betting_opportunities(fanduel_opportunities)
