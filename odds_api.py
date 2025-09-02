import requests
import datetime
import os
import json
from config import API_KEY, EVENTS_URL, POSITION_STAT_CONFIG, STAT_MARKET_MAPPING_YAHOO, DATA_DIR

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
    event_odds_url = f"{EVENTS_URL}/{event_id}/odds?apiKey={API_KEY}&regions={regions}&markets={markets}"

    # Load the cached data
    cache = load_cached_data()

    # Check if we should use saved data
    if use_saved_data:
        print(f"Using cached data for URL: {event_odds_url}")
        return cache[event_odds_url]

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
    return [STAT_MARKET_MAPPING_YAHOO[stat] for stat in yahoo_stats if stat in STAT_MARKET_MAPPING_YAHOO]

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
        for player in roster["players"].values():
            nfl_team = player["editorial_team_full_name"]
            game_id = get_game_id_from_team_name(nfl_team)
            if game_id not in games:
                games[game_id] = {"players": []}
            games[game_id]["players"].append(player)
    return games

# Fetch odds for all games and filter markets based on player positions
def fetch_odds_for_all_games(rosters=None, use_saved_data=True):
    """
    Fetches odds for all NFL games based on either the players in the roster (if provided) or all upcoming games.
    If 'rosters' is None, fetch odds for all games that haven't commenced yet.
    
    Args:
        rosters (list or None): The user lineups/rosters from Yahoo or None to fetch all games.
        use_saved_data (bool): Whether to use saved data or fetch fresh data.

    Returns:
        dict: Odds data for players across all games.
    """
    all_event_odds = {}
    
    if rosters:
        # If rosters are provided, group players by NFL game
        grouped_games = group_players_by_game(rosters)
    else:
        # If no rosters are provided, fetch all NFL games that have not started yet
        grouped_games = fetch_upcoming_nfl_games()

    for game_id, game_info in grouped_games.items():
        print(f"Fetching odds for game_id: {game_id}")

        # For each game, get the necessary markets based on the players' positions
        markets_to_fetch = set()

        if rosters:
            # Fetch markets based on players in rosters if provided
            for player in game_info["players"]:
                position = player["primary_position"]
                markets = get_required_markets_for_position(position)
                markets_to_fetch.update(markets)
        else:
            # Fetch all available markets for games when rosters are not provided
            markets_to_fetch = set(STAT_MARKET_MAPPING_YAHOO.values())

        markets_to_fetch = sorted(markets_to_fetch)
        markets_str = ",".join(markets_to_fetch)

        # Fetch event player odds for the game
        event_odds = get_event_player_odds(event_id=game_id, markets=markets_str, use_saved_data=use_saved_data)

        if event_odds:
            all_event_odds[game_id] = event_odds  # Store odds by event ID

    return all_event_odds

def fetch_upcoming_nfl_games():
    """
    Fetches all NFL games that have not yet commenced from TheOddsAPI.
    
    Returns:
        dict: A dictionary of NFL games with game IDs and team information.
    """
    nfl_events = get_nfl_events()
    upcoming_games = {}

    current_time = datetime.datetime.utcnow()

    for event in nfl_events:
        commence_time = datetime.datetime.strptime(event['commence_time'], "%Y-%m-%dT%H:%M:%SZ")
        if commence_time > current_time:
            game_id = event['id']
            upcoming_games[game_id] = {
                "home_team": event["home_team"],
                "away_team": event["away_team"],
                "commence_time": event["commence_time"],
                "players": []  # No player data if we're fetching for all games
            }

    return upcoming_games


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


def identify_betting_opportunities_on_fanduel(all_player_odds):
    """
    Identify betting opportunities where FanDuel offers significantly better odds than other sportsbooks.

    Args:
        all_player_odds (dict): Odds data for all players across different sportsbooks.
    
    Returns:
        list: A sorted list of betting opportunities where FanDuel has significantly better odds.
    """
    opportunities = []

    # Loop through each game
    for game_id, game_odds in all_player_odds.items():
        # Loop through each bookmaker for the game
        for bookmaker in game_odds["bookmakers"]:
            bookmaker_key = bookmaker["key"]

            # Check if FanDuel is available in the game
            if bookmaker_key == "fanduel":
                fanduel_odds = bookmaker["markets"]

                # Compare FanDuel odds with other sportsbooks
                for market in fanduel_odds:
                    market_key = market["key"]

                    for outcome in market["outcomes"]:
                        player_name = outcome["description"]
                        fanduel_price = outcome["price"]

                        # Compare FanDuel odds with other sportsbooks
                        for other_bookmaker in game_odds["bookmakers"]:
                            other_bookmaker_key = other_bookmaker["key"]
                            if other_bookmaker_key == "fanduel":
                                continue  # Skip FanDuel comparison with itself

                            # Find the corresponding market in other sportsbooks
                            for other_market in other_bookmaker["markets"]:
                                if other_market["key"] == market_key:
                                    for other_outcome in other_market["outcomes"]:
                                        if other_outcome["description"] == player_name:
                                            other_price = other_outcome["price"]

                                            # Calculate the percentage difference in odds
                                            percentage_diff = ((other_price - fanduel_price) / fanduel_price) * 100

                                            # If FanDuel's odds are significantly better, add to opportunities
                                            if percentage_diff > 0:
                                                opportunities.append({
                                                    "player_name": player_name,
                                                    "market": market_key,
                                                    "fanduel_odds": fanduel_price,
                                                    "other_odds": other_price,
                                                    "other_bookmaker": other_bookmaker_key,
                                                    "difference": percentage_diff
                                                })

    # Sort the opportunities by the most significant difference
    sorted_opportunities = sorted(opportunities, key=lambda x: x["difference"], reverse=True)
    return sorted_opportunities