from pprint import pprint
import odds_api
import json
import requests


def calculate_ev_for_fanduel(odds_data, fanduel_key="fanduel"):
    """
    Identify the best betting opportunities on FanDuel by comparing its odds and thresholds
    against the average odds and thresholds of other sportsbooks.
    
    Args:
        odds_data (dict): The odds data for all games.
        fanduel_key (str): The key used to identify FanDuel in the odds data.
    
    Returns:
        list: A sorted list of betting opportunities on FanDuel with higher expected value (EV).
    """
    betting_opportunities = []

    for game_id, game_info in odds_data.items():
        for bookmaker in game_info["bookmakers"]:
            if bookmaker["key"] == fanduel_key:
                fanduel_markets = bookmaker["markets"]

                for market in fanduel_markets:
                    fanduel_market_key = market["key"]
                    fanduel_outcomes = market["outcomes"]

                    for outcome in fanduel_outcomes:
                        fanduel_player = outcome["description"]
                        fanduel_odds = outcome["price"]
                        fanduel_threshold = outcome.get("point", 0)
                        fanduel_bet_type = outcome["name"]  # This could be 'Over' or 'Under'

                        # Gather data from other sportsbooks
                        odds_other_books = []
                        thresholds_other_books = []

                        for other_bookmaker in game_info["bookmakers"]:
                            if other_bookmaker["key"] != fanduel_key:
                                for other_market in other_bookmaker["markets"]:
                                    if other_market["key"] == fanduel_market_key:
                                        for other_outcome in other_market["outcomes"]:
                                            if other_outcome["description"] == fanduel_player and other_outcome["name"] == fanduel_bet_type:
                                                odds_other_books.append(other_outcome["price"])
                                                thresholds_other_books.append(other_outcome.get("point", 0))

                        if odds_other_books:
                            # Calculate the average odds and threshold from other books
                            avg_odds = sum(odds_other_books) / len(odds_other_books)
                            avg_threshold = sum(thresholds_other_books) / len(thresholds_other_books)

                            # Calculate the EV of FanDuel based on its odds and average threshold/odds from other books
                            ev = (1 / avg_odds) * fanduel_odds - 1

                            betting_opportunities.append({
                                "player": fanduel_player,
                                "market": fanduel_market_key,
                                "bet_type": fanduel_bet_type,  # Over/Under
                                "fanduel_odds": round(fanduel_odds, 3),
                                "fanduel_threshold": round(fanduel_threshold, 3),
                                "avg_odds_other_books": round(avg_odds, 3),
                                "avg_threshold_other_books": round(avg_threshold, 3),
                                "ev": round(ev, 3)
                            })

    # Sort betting opportunities by highest EV (positive EV values)
    sorted_opportunities = sorted(betting_opportunities, key=lambda x: x["ev"], reverse=True)
    return sorted_opportunities


def display_betting_opportunities(use_saved_data=True):
    """
    Fetch and display the best betting opportunities on FanDuel.
    """
    try:
        # Fetch odds for all NFL games
        all_player_odds = odds_api.fetch_odds_for_all_games(use_saved_data=use_saved_data)
        
        # Get the best opportunities for FanDuel
        opportunities = calculate_ev_for_fanduel(all_player_odds)

        # Display the results
        print(f"{'Player':<20} | {'Market':<20} | {'Bet Type':<10} | {'FanDuel Odds':<15} | {'FanDuel Threshold':<20} | {'Avg Odds Other Books':<20} | {'Avg Threshold Other Books':<25} | {'EV':<10}")
        print("-" * 160)
        for opp in opportunities:
            print(f"{opp['player']:<20} | {opp['market']:<20} | {opp['bet_type']:<10} | {opp['fanduel_odds']:<15} | {opp['fanduel_threshold']:<20} | {opp['avg_odds_other_books']:<20} | {opp['avg_threshold_other_books']:<25} | {opp['ev']:<10.3f}")

    except requests.exceptions.RequestException as e:
        print(f"ERROR when making API request: {e}")
        print(f"Response: {e.response.text}")
        print(f"URL Requested: {e.request.url}")


if __name__ == "__main__":
    # Set `use_saved_data=True` to use cached odds data; set it to `False` to fetch fresh data
    display_betting_opportunities(use_saved_data=True)
