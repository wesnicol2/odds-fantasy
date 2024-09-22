# odds_api.py

import requests
from config import API_KEY, EVENTS_URL
import json
from config import DATA_DIR

# Fetch NFL Events
def get_nfl_events(regions='us'):
    """
    Fetches upcoming NFL events (games) with event IDs from TheOddsAPI.
    
    Args:
        regions (str): The region for odds (default is 'us').
    
    Returns:
        list: A list of NFL events with event IDs.
    """
    url = f"{EVENTS_URL}?apiKey={API_KEY}&regions={regions}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


# Fetch player odds for a specific event
def get_event_player_odds(event_id, regions='us', markets='player_rush_yds,player_reception_yds,player_pass_tds,player_pass_yds'):
    """
    Fetches player-specific odds for a given NFL event using the event-odds endpoint.
    
    Args:
        event_id (str): The event ID of the NFL game.
        regions (str): The region for odds (default is 'us').
        markets (str): The player prop markets to fetch (e.g., rushing yards, passing touchdowns).
    
    Returns:
        dict: Odds data for players in the specific NFL event.
    """
    event_odds_url = f"{EVENTS_URL}/{event_id}/odds?apiKey={API_KEY}&regions={regions}&markets={markets}"
    response = requests.get(event_odds_url)
    response.raise_for_status()
    return response.json()


# Fetch odds for all events
def get_all_event_odds(events):
    """
    Fetches player-specific odds for all upcoming NFL events (games).
    
    Args:
        events (list): List of events (games) with event IDs.
    
    Returns:
        dict: A dictionary containing player-specific odds for all games.
    """
    all_event_odds = {}
    
    for event in events:
        event_id = event['id']
        print(f"Fetching odds for event: {event['home_team']} vs {event['away_team']} (ID: {event_id})")
        event_odds = get_event_player_odds(event_id=event_id)
        
        if event_odds:
            all_event_odds[event_id] = event_odds  # Store odds by event ID

    return all_event_odds


# Process and organize player odds
def get_all_player_odds(all_event_odds):
    """
    Processes all event odds and returns a dictionary with player names as keys and their odds across markets.
    
    Args:
        all_event_odds (dict): A dictionary containing event-specific odds.
    
    Returns:
        dict: A dictionary where player names are the primary keys, and all known odds for all known markets are stored under their names.
    """
    player_odds_dict = {}

    for event_id, event_odds in all_event_odds.items():
        for bookmaker in event_odds['bookmakers']:
            bookmaker_name = bookmaker['key']
            for market in bookmaker['markets']:
                market_key = market['key']  # e.g., player_pass_yds, player_rush_yds
                
                for outcome in market['outcomes']:
                    player_name = outcome['description']  # The player's name from the "description" field
                    point_value = outcome.get('point', None)  # Point (over/under threshold)
                    price = outcome['price']  # Odds value
                    outcome_type = outcome['name'].lower()  # "Over" or "Under"

                    if player_name not in player_odds_dict:
                        player_odds_dict[player_name] = {}

                    if bookmaker_name not in player_odds_dict[player_name]:
                        player_odds_dict[player_name][bookmaker_name] = {}

                    if market_key not in player_odds_dict[player_name][bookmaker_name]:
                        player_odds_dict[player_name][bookmaker_name][market_key] = {"over": None, "under": None}

                    player_odds_dict[player_name][bookmaker_name][market_key][outcome_type] = {
                        "odds": price,
                        "point": point_value
                    }

    return player_odds_dict


# Save player odds to file
def save_player_odds(player_odds, filename=f'{DATA_DIR}/all_player_odds.json'):
    """
    Saves the player odds dictionary to a JSON file.
    
    Args:
        player_odds (dict): The player odds data to save.
        filename (str): The name of the file where the data will be saved.
    """
    try:
        with open(filename, 'w') as f:
            json.dump(player_odds, f, indent=4)
        print(f"Player odds data successfully saved to {filename}.")
    except IOError as e:
        print(f"Error saving player odds to file: {e}")


# Load player odds from file
def load_player_odds(filename=f'{DATA_DIR}/all_player_odds.json'):
    """
    Loads the player odds data from a JSON file.
    
    Args:
        filename (str): The name of the file to load the data from.
    
    Returns:
        dict: The player odds data if successfully loaded, otherwise an empty dictionary.
    """
    try:
        with open(filename, 'r') as f:
            player_odds = json.load(f)
        print(f"Player odds data successfully loaded from {filename}.")
        return player_odds
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading player odds from file: {e}")
        return {}


def refresh_odds():
    """
    Fetches and saves the latest NFL odds for all upcoming games and players.
    """
    try:
        events = get_nfl_events()
        all_event_odds = get_all_event_odds(events)
        all_player_odds = get_all_player_odds(all_event_odds)
        save_player_odds(all_player_odds)
        print("Saved Player Odds")
    except requests.exceptions.RequestException as e:
        print(f"ERROR when making API request: {e}")
        print(f"URL Requested: {e.request.url}")