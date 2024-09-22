import requests
from pprint import pprint
import os
from dotenv import load_dotenv
import json

# Load environment variables from the .env file
load_dotenv()

# Fetch the API key from environment variables
API_KEY = os.getenv('API_KEY')

if not API_KEY:
    raise ValueError("API_KEY is not set. Please ensure it is set in the environment or the .env file.")

BASE_URL = 'https://api.the-odds-api.com/v4'
EVENTS_URL = f'{BASE_URL}/sports/americanfootball_nfl/events'
DATA_DIR = "./data"

def get_nfl_events(api_key=API_KEY, regions='us'):
    """
    Fetches upcoming NFL events (games) with event IDs from TheOddsAPI.
    
    Args:
        api_key (str): TheOddsAPI key for authentication.
        regions (str): The region for odds (default is 'us').
    
    Returns:
        list: A list of NFL events with event IDs.
    """
    
    url = f"{EVENTS_URL}?apiKey={api_key}&regions={regions}"
    response = requests.get(url)
    response.raise_for_status()
    events = response.json()  # Parse the response as JSON
    return events


def get_event_player_odds(event_id, api_key=API_KEY, regions='us', markets='player_rush_yds,player_reception_yds,player_pass_tds,player_pass_yds'):
    """
    Fetches player-specific odds for a given NFL event using the event-odds endpoint.
    
    Args:
        api_key (str): TheOddsAPI key for authentication.
        event_id (str): The event ID of the NFL game.
        regions (str): The region for odds (default is 'us').
        markets (str): The player prop markets to fetch (e.g., rushing yards, passing touchdowns).
    
    Returns:
        dict: Odds data for players in the specific NFL event.
    """
    EVENT_ODDS_URL = f'{BASE_URL}/sports/americanfootball_nfl/events'
    url = f"{EVENT_ODDS_URL}/{event_id}/odds?apiKey={api_key}&regions={regions}&markets={markets}"
    response = requests.get(url)
    response.raise_for_status()  # Check for a successful response
    event_odds = response.json()  # Parse the response as JSON
    return event_odds


def get_all_event_odds(events, api_key=API_KEY):
    """
    Fetches player-specific odds for all upcoming NFL events (games).
    
    Args:
        api_key (str): TheOddsAPI key for authentication.
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


def get_all_player_odds(all_event_odds):
    """
    Processes all event odds and returns a dictionary with player names as keys and their odds across markets.
    
    Args:
        all_event_odds (dict): A dictionary containing event-specific odds.
    
    Returns:
        dict: A dictionary where player names are the primary keys, and all known odds for all known markets are stored under their names.
    """
    player_odds_dict = {}

    # Iterate over each event's odds
    for event_id, event_odds in all_event_odds.items():
        for bookmaker in event_odds['bookmakers']:
            bookmaker_name = bookmaker['key']
            for market in bookmaker['markets']:
                market_key = market['key']  # e.g., player_pass_yds, player_rush_yds
                
                for outcome in market['outcomes']:
                    player_name = outcome['description']  # The player's name from the "description" field
                    point_value = outcome.get('point', None)  # Point (over/under threshold), if available
                    price = outcome['price']  # Odds value
                    outcome_type = outcome['name'].lower()  # Typically "Over" or "Under"

                    # Ensure player is added to the dictionary
                    if player_name not in player_odds_dict:
                        player_odds_dict[player_name] = {}

                    if bookmaker_name not in player_odds_dict[player_name]:
                        player_odds_dict[player_name][bookmaker_name] = {}

                    # Ensure the market is added for the player
                    if market_key not in player_odds_dict[player_name]:
                        player_odds_dict[player_name][bookmaker_name][market_key] = {"over": None, "under": None}

                    # Add odds for "over" or "under"
                    player_odds_dict[player_name][bookmaker_name][market_key][outcome_type] = {
                        "odds": price,
                        "point": point_value
                    }

    return player_odds_dict


def save_player_odds(player_odds, filename=f'{DATA_DIR}/all_player_odds.json'):
    """
    Saves the player odds dictionary to a JSON file.
    
    Args:
        player_odds (dict): The player odds data to save.
        filename (str): The name of the file where the data will be saved (default is {DATA_DIR}/all_player_odds.json).
    """
    try:
        with open(filename, 'w') as f:
            json.dump(player_odds, f, indent=4)
        print(f"Player odds data successfully saved to {filename}.")
    except IOError as e:
        print(f"Error saving player odds to file: {e}")


def load_player_odds(filename=f'{DATA_DIR}/all_player_odds.json'):
    """
    Loads the player odds data from a JSON file.
    
    Args:
        filename (str): The name of the file to load the data from (default is {DATA_DIR}/all_player_odds.json).
    
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
    try: 
        events = get_nfl_events()
        all_event_odds = get_all_event_odds(events)
        all_player_odds = get_all_player_odds(all_event_odds)
        save_player_odds(all_player_odds)
        print("Saved Player Odds")
    except requests.exceptions.RequestException as e:
            print(f"ERROR when making API request: {e}")
            print(f"URL Requested: {e.request.url}")
            print("Response:")
            pprint(e.response.json())


# Example usage of loading saved odds:
all_player_odds = load_player_odds()
player_names = ["Joe Burrow", "Drake London", "Zach Charbonnet", "Sam LaPorta"]
for player_name in player_names:
    if player_name in all_player_odds.keys():
        print(player_name + " Odds:")
        pprint(all_player_odds[player_name])