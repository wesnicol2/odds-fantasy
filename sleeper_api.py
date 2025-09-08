import requests
from config import SLEEPER_TO_ODDSAPI_TEAM

SLEEPER_BASE_URL = "https://api.sleeper.app/v1"
REQ_TIMEOUT = (5, 20)  # (connect, read) seconds


def get_player_enhanced_info(player_id):
        """
        Given a Sleeper player ID and the players metadata dict, return a dict with:
            - full_name: Player's full name (for Odds API matching)
            - team: NFL team (abbreviation or full name as available)
            - position: Player's position
        """
        players_metadata = get_players()
        pdata = players_metadata.get(player_id, {})
        # TODO: Convert sleeper format to format which fits odds api here
        return {
            "editorial_team_full_name": SLEEPER_TO_ODDSAPI_TEAM.get(pdata.get("team")),  # or map to full team name if needed
            "primary_position": pdata.get("position"),
            "name": {"full": pdata.get("full_name", player_id)},
            # add more fields if needed
    }

def get_enhanced_info_for_roster(roster):
    """
    Given a Sleeper roster dict, return a new dict with player IDs as keys and
    as much info as needed (name, team, position, etc...)
    """
    enhanced_roster = {}
    for pid in roster.get('players', []):
        enhanced_roster[pid] = get_player_enhanced_info(pid)
    return enhanced_roster
        

def get_user_sleeper_data(username, season):
    """
    Fetch the roster for a user (by username) for their first league in a given season.
    Returns the roster dict, or None if not found.
    """
    user_id = get_user_id(username)
    leagues = get_user_leagues(user_id, season)
    if not leagues:
        return None
    league_id = leagues[0]['league_id'] # TODO: Enhance to handle multiple leagues
    rosters = get_league_rosters(league_id)
    scoring_settings = leagues[0].get('scoring_settings', {})
    for roster in rosters:
        if roster.get('owner_id') == user_id:
            enhanced_roster = get_enhanced_info_for_roster(roster)
            return {
                'players': enhanced_roster,
                'scoring_rules': scoring_settings
            }
    return None


def get_user_id(username):
    """
    Fetch the Sleeper user ID for a given username.
    """
    url = f"{SLEEPER_BASE_URL}/user/{username}"
    response = requests.get(url, timeout=REQ_TIMEOUT)
    response.raise_for_status()
    return response.json()["user_id"]


def get_user_leagues(user_id, season):
    """
    Fetch all leagues for a user in a given season.
    """
    url = f"{SLEEPER_BASE_URL}/user/{user_id}/leagues/nfl/{season}"
    response = requests.get(url, timeout=REQ_TIMEOUT)
    response.raise_for_status()
    return response.json()


def get_league_rosters(league_id):
    """
    Fetch all rosters for a given league.
    """
    url = f"{SLEEPER_BASE_URL}/league/{league_id}/rosters"
    response = requests.get(url, timeout=REQ_TIMEOUT)
    response.raise_for_status()
    return response.json()


def get_players():
    """
    Fetch all NFL player metadata from Sleeper.
    """
    url = f"{SLEEPER_BASE_URL}/players/nfl"
    response = requests.get(url, timeout=REQ_TIMEOUT)
    response.raise_for_status()
    return response.json()

def get_available_defenses(username, season):
    # 1. Get all player metadata
    all_players = get_players()
    all_defenses = {pid: pdata for pid, pdata in all_players.items() if pdata.get("position") == "DEF"}

    # 2. Get all rosters in the league
    user_id = get_user_id(username)
    leagues = get_user_leagues(user_id, season)
    league_id = leagues[0]['league_id'] # TODO: Enhance to handle multiple leagues
    rosters = get_league_rosters(league_id)
    owned_def_ids = set()
    for roster in rosters:
        for pid in roster.get("players", []):
            if pid in all_defenses:
                owned_def_ids.add(pid)

    # 3. Find unowned defenses
    available_defenses = {pid: pdata for pid, pdata in all_defenses.items() if pid not in owned_def_ids}
    return available_defenses
