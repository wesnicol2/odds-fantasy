import odds_api
import requests
import tkinter as tk
from tkinter import ttk
from datetime import datetime

def implied_probability(odds):
    """Converts decimal odds to implied probability."""
    return 1 / odds

def consensus_probability(odds_list):
    """Calculates the consensus probability by averaging implied probabilities of a list of odds."""
    total_probability = sum(implied_probability(odds) for odds in odds_list)
    return total_probability / len(odds_list)

def calculate_ev(fanduel_odds, consensus_prob):
    """Calculate the expected value (EV) of FanDuel odds based on the consensus probability."""
    return (consensus_prob * fanduel_odds) - 1


def is_future_date(date_str):
    # Parse the input date string with format '%Y-%m-%dT%H:%M:%SZ'
    given_date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%SZ')
    
    # Get the current UTC time
    current_time = datetime.utcnow()
    
    # Check if the given date is in the future
    return given_date > current_time


def aggregate_consensus_data(odds_data, fanduel_key="fanduel"):
    """Aggregate consensus probabilities and thresholds from all sportsbooks (except FanDuel) and compare them to FanDuel's odds."""
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
                        fanduel_bet_type = outcome["name"]
                        fanduel_game_time = game_info["commence_time"]

                        # Gather odds and thresholds from other sportsbooks
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
                            # Calculate consensus probability and threshold from other books
                            consensus_prob = consensus_probability(odds_other_books)
                            avg_threshold_other_books = sum(thresholds_other_books) / len(thresholds_other_books)

                            # Calculate EV for FanDuel odds
                            ev = calculate_ev(fanduel_odds, consensus_prob)

                            betting_opportunities.append({
                                "player": fanduel_player,
                                "market": fanduel_market_key,
                                "bet_type": fanduel_bet_type,
                                "fanduel_odds": round(fanduel_odds, 3),
                                "fanduel_threshold": round(fanduel_threshold, 3),
                                "avg_odds_other_books": round(1 / consensus_prob, 3),
                                "avg_threshold_other_books": round(avg_threshold_other_books, 3),
                                "ev": round(ev, 3),
                                "commence_time": fanduel_game_time
                            })

    # Sort betting opportunities by highest EV
    return sorted(betting_opportunities, key=lambda x: x["ev"], reverse=True)

def display_betting_opportunities_gui(use_saved_data=True):
    """Fetch and display the best betting opportunities on FanDuel in a pop-up window with fixed column widths."""
    try:
        # Fetch odds for all NFL games
        all_player_odds = odds_api.fetch_odds_for_all_games(use_saved_data=use_saved_data)

        # Get the best opportunities for FanDuel
        opportunities = aggregate_consensus_data(all_player_odds)

        # Create Tkinter window
        root = tk.Tk()
        root.title("Betting Opportunities on FanDuel")

        # Create frame for table
        frame = ttk.Frame(root)
        frame.pack(fill=tk.BOTH, expand=False)

        # Define column headers
        headings = ["EV", "Player", "Market", "Bet Type", "FanDuel Threshold", "FanDuel Odds", "Avg Threshold Other Books", "Avg Odds Other Books", "Game Commence Time"]

        # Create a treeview widget (table)
        tree = ttk.Treeview(frame, columns=headings, show="headings")

        # Set column widths to fixed values
        column_widths = {
            "EV": 100, "Player": 150, "Market": 120, "Bet Type": 100,
            "FanDuel Threshold": 120, "FanDuel Odds": 120, 
            "Avg Threshold Other Books": 150, "Avg Odds Other Books": 150,
            "Game Commence Time": 100
        }

        # Insert data into the table and set fixed column widths
        for col in headings:
            tree.heading(col, text=col)
            tree.column(col, width=column_widths[col], anchor=tk.CENTER)

        for opp in opportunities:
            if is_future_date(opp["commence_time"]):
                tree.insert("", tk.END, values=(
                    opp['ev'], opp['player'], opp['market'], opp['bet_type'],  opp['fanduel_threshold'], opp['fanduel_odds'],
                    opp['avg_threshold_other_books'], opp['avg_odds_other_books'],
                    opp["commence_time"]
                ))

        # Create vertical scrollbar
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Pack the treeview widget
        tree.pack(fill=tk.BOTH, expand=True)

        # Run the Tkinter event loop
        root.mainloop()

    except requests.exceptions.RequestException as e:
        print(f"ERROR when making API request: {e}")
        print(f"Response: {e.response.text}")

if __name__ == "__main__":
    # Set `use_saved_data=True` to use cached odds data; set it to `False` to fetch fresh data
    display_betting_opportunities_gui(use_saved_data=True)
