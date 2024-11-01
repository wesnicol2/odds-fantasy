import requests
import os
import json
from config import API_KEY, EVENTS_URL, POSITION_STAT_CONFIG, STAT_MARKET_MAPPING, DATA_DIR

# Path for the cache file
CACHE_FILE = os.path.join(DATA_DIR, "odds_api_cache.json")

# Helper: Load cached data
def load_cached_data():
    """
    Loads the cached API responses from a JSON file.

    Returns:
        dict: Cached data where keys are URLs and values are responses.
    """
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            print(f"Error loading cached data: {e}")
            return {}
    return {}

# Helper: Save data to cache
def save_cached_data(cache):
    """
    Saves the given cache dictionary to a JSON file.

    Args:
        cache (dict): The cache dictionary to save.
    """
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=4)
        print(f"Cached data successfully saved to {CACHE_FILE}.")
    except IOError as e:
        print(f"Error saving cached data: {e}")


def sort_csv_string(input_string):
    # Split the string by commas into a list
    values = input_string.split(',')
    # Sort the list alphabetically (case-insensitive)
    sorted_values = sorted(values, key=str.lower)
    # Join the sorted list back into a comma-separated string
    return ','.join(sorted_values)


# Fetch player odds for a specific event
def get_event_player_odds(event_id, regions='us', markets='player_rush_yds,player_reception_yds,player_pass_tds,player_pass_yds', use_saved_data=True):
    """
    Fetches player-specific odds for a given NFL event using the event-odds endpoint.
    Caches the request URL and response, and uses saved data if available.

    Args:
        event_id (str): The event ID of the NFL game.
        regions (str): The region for odds (default is 'us').
        markets (str): The player prop markets to fetch (e.g., rushing yards, passing touchdowns).
        use_saved_data (bool): Whether to use saved data or fetch fresh data.

    Returns:
        dict: Odds data for players in the specific NFL event.
    """
    markets = sort_csv_string(markets)
    event_odds_url = f"{EVENTS_URL}/{event_id}/odds?apiKey={API_KEY}&regions={regions}&markets={markets}"

    # Load the cached data
    cache = load_cached_data()

    # Check if we should use saved data
    if use_saved_data:
        print(f"Using cached data for URL: {event_odds_url}")
        return cache.get(event_odds_url, None)

    # Make the API request if not cached or if fresh data is required
    response = requests.get(event_odds_url)
    response.raise_for_status()

    # Cache the new response
    cache[event_odds_url] = response.json()
    save_cached_data(cache)

    return response.json()


# Helper: Get required markets for a player based on their position
def get_required_markets_for_position(position):
    """
    Returns a list of markets (stat categories) that are relevant for a given position.
    
    Args:
        position (str): The player's position (e.g., QB, RB).
    
    Returns:
        list: A list of markets relevant for the position (e.g., 'player_pass_yds').
    """
    yahoo_stats = POSITION_STAT_CONFIG.get(position, [])
    return [STAT_MARKET_MAPPING[stat] for stat in yahoo_stats if stat in STAT_MARKET_MAPPING]


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


# Fetch odds for all games and filter markets based on player positions
def fetch_odds_for_all_games(rosters=None, use_saved_data=True):
    """
    Fetches odds for all games based on the players in the roster and their positions.
    Uses saved data if available, otherwise fetches fresh data.

    Args:
        rosters (list): The user lineups/rosters from Yahoo or None to get all games.
        use_saved_data (bool): Whether to use saved data or fetch fresh data.

    Returns:
        dict: Odds data for players across all games.
    """
    all_event_odds = {}

    if rosters is None:
        # Fetch all upcoming games when no roster is provided
        events = get_nfl_events()
        for event in events:
            game_id = event['id']
            event_odds = get_event_player_odds(event_id=game_id, use_saved_data=use_saved_data)
            if event_odds:
                all_event_odds[game_id] = event_odds
    else:
        # Fetch games relevant to the roster players
        grouped_games = group_players_by_game(rosters)

        for game_id, game_info in grouped_games.items():
            print(f"Fetching odds for game_id: {game_id}")

            # For each game, get the necessary markets based on the players' positions
            markets_to_fetch = set()
            for player in game_info["players"]:
                position = player["primary_position"]
                markets = get_required_markets_for_position(position)
                markets_to_fetch.update(markets)
            
            markets_to_fetch = sorted(markets_to_fetch)
            markets_str = ",".join(markets_to_fetch)
            event_odds = get_event_player_odds(event_id=game_id, markets=markets_str, use_saved_data=use_saved_data)

            if event_odds:
                all_event_odds[game_id] = event_odds  # Store odds by event ID

    return all_event_odds

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
