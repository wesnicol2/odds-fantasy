import requests
from config import API_KEY, EVENTS_URL, POSITION_STAT_CONFIG
import json
from config import DATA_DIR

# Helper: Get required markets for a player based on their position
def get_required_markets_for_position(position):
    """
    Returns a list of markets (stat categories) that are relevant for a given position.
    
    Args:
        position (str): The player's position (e.g., QB, RB).
    
    Returns:
        list: A list of markets relevant for the position (e.g., 'player_pass_yds').
    """
    return POSITION_STAT_CONFIG.get(position, [])


def get_game_id_from_team_name(team_name):
    """
    Fetches the game ID for the specified team from the list of NFL events.

    Args:
        team_name (str): The full name of the NFL team (e.g., "Kansas City Chiefs").

    Returns:
        str: The game ID for the team's next NFL game, or None if no match is found.
    """
    nfl_events = get_nfl_events()
    
    for event in nfl_events:
        if team_name == event['home_team'] or team_name == event['away_team']:
            return event['id']
    
    print(f"Team '{team_name}' not found in any upcoming games.")
    return None


# Group players by NFL game to minimize API requests
def group_players_by_game(rosters):
    """
    Groups players by their NFL game to avoid redundant API requests.

    Args:
        rosters (list): List of rosters with players.

    Returns:
        dict: Grouped players by game, where each key is a game ID.
    """
    games = {}
    for roster in rosters:
        for player in roster["players"]["player"]:
            nfl_team = player["editorial_team_full_name"]
            game_id = get_game_id_from_team_name(nfl_team)
            if game_id not in games:
                games[game_id] = {"players": []}
            games[game_id]["players"].append(player)
    return games

# Fetch odds for all games and filter markets based on player positions
def fetch_odds_for_all_games(rosters, use_saved_data=True):
    """
    Fetches odds for all games based on the players in the roster and their positions.
    
    Args:
        rosters (list): The user lineups/rosters from Yahoo.
        use_saved_data (bool): Whether to use saved data or fetch fresh data.

    Returns:
        dict: Odds data for players across all games.
    """
    if use_saved_data:
        print("Loading saved player odds...")
        return load_player_odds()  # Return saved data if available

    all_event_odds = {}
    grouped_games = group_players_by_game(rosters)

    for game_id, game_info in grouped_games.items():
        print(f"Fetching odds for game_id: {game_id}")
        
        # For each game, get the necessary markets based on the players' positions
        markets_to_fetch = set()
        for player in game_info["players"]:
            position = player["primary_position"] # TODO: expand this to use all possible positions (TAYSOM HILL BABY) 
            markets = get_required_markets_for_position(position)
            markets_to_fetch.update(markets)
        
        markets_str = ",".join(markets_to_fetch)
        event_odds = get_event_player_odds(event_id=game_id, markets=markets_str)

        if event_odds:
            all_event_odds[game_id] = event_odds  # Store odds by event ID

    return all_event_odds


# Quota Cost Calculator
def calculate_quota_cost(markets, regions):
    """
    Calculates the expected quota cost for a request based on the number of unique markets and regions.
    
    Args:
        markets (str): Comma-separated string of markets (e.g., 'player_rush_yds,player_pass_tds').
        regions (str): Comma-separated string of regions (e.g., 'us').
    
    Returns:
        int: The calculated quota cost.
    """
    num_markets = len(markets.split(","))
    num_regions = len(regions.split(","))
    return num_markets * num_regions


# Fetch player odds for a specific event
def get_event_player_odds(event_id, regions='us', markets='player_rush_yds,player_reception_yds,player_pass_tds,player_pass_yds'):
    """
    Fetches player-specific odds for a given NFL event using the event-odds endpoint.
    Calculates the quota cost and asks for user confirmation before making the request.

    Args:
        event_id (str): The event ID of the NFL game.
        regions (str): The region for odds (default is 'us').
        markets (str): The player prop markets to fetch (e.g., rushing yards, passing touchdowns).

    Returns:
        dict: Odds data for players in the specific NFL event.
    """
    event_odds_url = f"{EVENTS_URL}/{event_id}/odds?apiKey={API_KEY}&regions={regions}&markets={markets}"

    # Calculate the quota cost before making the request
    estimated_cost = calculate_quota_cost(markets, regions)
    
    # Prompt the user to confirm if they want to proceed
    confirmation = input(f"The estimated quota cost for this request is {estimated_cost}. Do you want to proceed? (yes/no): ")
    if confirmation.lower() != 'yes':
        print("Request canceled.")
        return None

    # Make the API request
    response = requests.get(event_odds_url)
    response.raise_for_status()
    
    # Get quota-related headers
    quota_cost = int(response.headers.get('x-requests-last', 0))
    requests_remaining = response.headers.get('x-requests-remaining', 'unknown')
    requests_used = response.headers.get('x-requests-used', 'unknown')

    # Display quota usage details to the user
    print(f"Quota cost of this request: {quota_cost}")
    print(f"Requests remaining: {requests_remaining}")
    print(f"Total requests used: {requests_used}")
    
    return response.json()


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
