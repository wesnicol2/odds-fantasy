import requests
from pprint import pprint

# TheOddsAPI configuration
API_KEY = 'YOUR_API_KEY_HERE'  # Replace with your TheOddsAPI key
BASE_URL = 'https://api.the-odds-api.com/v4'
EVENTS_URL = f'{BASE_URL}/sports/americanfootball_nfl/events'

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
    



def get_all_player_odds(events, api_key=API_KEY):
    """
    Fetches player-specific odds for all upcoming NFL events (games).
    
    Args:
        api_key (str): TheOddsAPI key for authentication.
        events (list): List of events (games) with event IDs.
    
    Returns:
        dict: A dictionary containing player-specific odds for all games.
    """
    all_player_odds = {}
    
    for event in events:
        event_id = event['id']
        print(f"Fetching odds for event: {event['home_team']} vs {event['away_team']} (ID: {event_id})")
        event_odds = get_event_player_odds(event_id=event_id)
        
        if event_odds:
            all_player_odds[event_id] = event_odds  # Store odds by event ID

    return all_player_odds


def print_player_odds_across_games(all_player_odds, player_names):
    """
    Prints the odds data for each player across all games.
    
    Args:
        all_player_odds (dict): Dictionary containing player-specific odds for all games.
        player_names (list): List of player names to retrieve odds for.
    """
    for event_id, event_odds in all_player_odds.items():
        print(f"\nEvent ID: {event_id}")
        for player_name in player_names:
            print(f"\nOdds for {player_name}:")
            
            for bookmaker in event_odds['bookmakers']:
                for market in bookmaker['markets']:
                    for outcome in market['outcomes']:
                        if player_name.lower() in outcome['description'].lower():
                            print(f"  Market: {market['key']}")
                            print(f"    {outcome['name']} - {outcome.get('point', 'N/A')} - Odds: {outcome['price']}")
                        
            # If no odds were found for the player
            if not any(player_name.lower() in outcome['name'].lower() for bookmaker in event_odds['bookmakers'] for market in bookmaker['markets'] for outcome in market['outcomes']):
                print(f"  No odds data available for {player_name}.")



try: 
    # events = get_nfl_events()
    events = [{'away_team': 'Washington Commanders',
  'commence_time': '2024-09-24T00:15:00Z',
  'home_team': 'Cincinnati Bengals',
  'id': '8e047915fdc9b7dc77d2276e740f55d2',
  'sport_key': 'americanfootball_nfl',
  'sport_title': 'NFL'}]
    all_player_odds = get_all_player_odds(events)
    player_names = ["Joe Burrow", "Drake London", "Zach Charbonnet", "Sam LaPorta"]
    print_player_odds_across_games(all_player_odds, player_names)
except requests.exceptions.RequestException as e:
        print(f"ERROR when making API request: {e}")
        print(f"URL Requested: {e.request.url}")
        print("Response:")
        pprint(e.response.json())



