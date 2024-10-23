import requests
from pprint import pprint
import tkinter as tk
from tkinter import ttk


# Constants for API access and configuration
API_KEY = 'a0e69988bfd96be1f874f7c50db9d6db'
API_URL = 'https://api.the-odds-api.com/v4/sports'
SPORT = 'americanfootball_nfl'
REGION = 'us'
MARKET = 'h2h'
BOOKMAKERS = ["betonlineag", "betmgm", "betrivers", "betus", "bovada", 
    "williamhill_us", "draftkings", "fanduel", "lowvig", "mybookieag", 
    "ballybet", "betanysports", "betparx", "espnbet", "fliff", 
    "hardrockbet", "windcreek"]


def display_positive_ev_bets_table(bets):
    """
    Display the positive EV bets in a UI table using Tkinter and ttk.
    Args:
        bets (list): A list of dictionaries containing positive EV bet data.
    """
    # Create the main window
    window = tk.Tk()
    window.title("Positive EV Bets")

    # Create a Treeview widget to display the bets as a table
    tree = ttk.Treeview(window, columns=('Team', 'FanDuel Odds', 'Implied Probability', 'Other Books Avg Prob', 'Expected Value'), show='headings')

    # Define the columns
    tree.heading('Team', text='Team')
    tree.heading('FanDuel Odds', text='FanDuel Odds')
    tree.heading('Implied Probability', text='Implied Probability')
    tree.heading('Other Books Avg Prob', text='Avg Prob from Other Books')
    tree.heading('Expected Value', text='Expected Value')

    # Adjust column widths
    tree.column('Team', width=150)
    tree.column('FanDuel Odds', width=100)
    tree.column('Implied Probability', width=150)
    tree.column('Other Books Avg Prob', width=150)
    tree.column('Expected Value', width=150)

    # Add data to the table
    for bet in bets:
        tree.insert('', tk.END, values=(
            bet['team'],
            bet['fanduel_odds'],
            f"{bet['fanduel_implied_prob']:.2%}",
            f"{bet['average_other_books_prob']:.2%}",
            f"{bet['expected_value']:.4f}"
        ))

    # Pack and display the table
    tree.pack(fill=tk.BOTH, expand=True)

    # Start the Tkinter main loop
    window.mainloop()


def fetch_odds(api_key, sport, region, market, bookmakers):
    url = f"{API_URL}/{sport}/odds"
    params = {
        'apiKey': api_key,
        'regions': region,
        'markets': market,
        'bookmakers': ','.join(bookmakers),
        'oddsFormat': 'american'
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching odds data: {e}")
        return None

def convert_american_to_implied_probability(odds):
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)

def extract_fanduel_odds(odds_data):
    fanduel_odds = {}
    for event in odds_data:
        markets = event['bookmakers']
        for bookmaker in markets:
            if bookmaker['key'] == 'fanduel':
                for market in bookmaker['markets']:
                    if market['key'] == 'h2h':
                        for outcome in market['outcomes']:
                            team = outcome['name']
                            odds = outcome['price']
                            implied_prob = convert_american_to_implied_probability(odds)
                            fanduel_odds[team] = {
                                'odds': odds,
                                'implied_prob': implied_prob
                            }
    return fanduel_odds

def calculate_ev(fanduel_odds, other_books_probs, team):
    avg_prob = sum(other_books_probs) / len(other_books_probs)
    odds = fanduel_odds[team]['odds']
    payout = odds / 100 if odds > 0 else 100 / abs(odds)
    prob_of_losing = 1 - avg_prob
    ev = (avg_prob * payout) - (prob_of_losing * 1)
    return ev

def extract_other_books_probs(odds_data, team):
    other_books_probs = []
    for event in odds_data:
        for bookmaker in event['bookmakers']:
            if bookmaker['key'] != 'fanduel':
                for market in bookmaker['markets']:
                    if market['key'] == 'h2h':
                        for outcome in market['outcomes']:
                            if outcome['name'] == team:
                                odds = outcome['price']
                                implied_prob = convert_american_to_implied_probability(odds)
                                other_books_probs.append(implied_prob)
    return other_books_probs

def filter_positive_ev_bets(fanduel_odds, odds_data):
    positive_ev_bets = []
    for team, odds_info in fanduel_odds.items():
        other_books_probs = extract_other_books_probs(odds_data, team)
        if not other_books_probs:
            continue
        ev = calculate_ev(fanduel_odds, other_books_probs, team)
        if ev is not None and ev > 0:
            positive_ev_bets.append({
                'team': team,
                'fanduel_odds': odds_info['odds'],
                'fanduel_implied_prob': odds_info['implied_prob'],
                'average_other_books_prob': sum(other_books_probs) / len(other_books_probs),
                'expected_value': ev
            })
    return positive_ev_bets

# Example usage to fetch odds, calculate EV, and filter positive EV bets
odds_data = fetch_odds(API_KEY, SPORT, REGION, MARKET, BOOKMAKERS)
fanduel_odds = extract_fanduel_odds(odds_data)
positive_ev_bets = filter_positive_ev_bets(fanduel_odds, odds_data)
sorted_positive_ev_bets = sorted(positive_ev_bets, key=lambda x: x['expected_value'])
display_positive_ev_bets_table(sorted_positive_ev_bets)
