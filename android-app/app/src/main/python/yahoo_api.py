import os
import json
from requests_oauthlib import OAuth2Session
from config import *
from oauthlib.oauth2.rfc6749.errors import TokenExpiredError
from pprint import pprint
import xmltodict


def save_token(token):
    """
    Save OAuth token to a file.
    Args:
        token (dict): The token dictionary to be saved.
    """
    with open(YAHOO_OAUTH_TOKEN_FILE, 'w') as f:
        json.dump(token, f)


def load_token():
    """
    Load OAuth token from a file if it exists.
    Returns:
        dict: The token dictionary, or None if not found.
    """
    if os.path.exists(YAHOO_OAUTH_TOKEN_FILE):
        with open(YAHOO_OAUTH_TOKEN_FILE, 'r') as f:
            return json.load(f)
    return None


def yahoo_oauth_login():
    """
    Handles the Yahoo OAuth 2.0 login flow.
    If a valid token exists, it will be loaded. Otherwise, it will authenticate the user.
    Returns:
        OAuth2Session: An authenticated session object.
    """
    # Check if a token already exists
    token = load_token()

    if token:
        print("Using saved token.")
        yahoo = OAuth2Session(YAHOO_CLIENT_ID, token=token)

        # Try to refresh the token if expired or close to expiring
        try:
            yahoo.get('https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1')
            return yahoo
        except TokenExpiredError:
            # Refresh the token
            print("Token expired, refreshing...")
            token = yahoo.refresh_token(YAHOO_TOKEN_URL, client_id=YAHOO_CLIENT_ID, client_secret=YAHOO_CLIENT_SECRET)
            save_token(token)
            return yahoo

    # If no token or expired, initiate OAuth login
    yahoo = OAuth2Session(YAHOO_CLIENT_ID, redirect_uri=YAHOO_REDIRECT_URI)

    # Step 1: Redirect user to Yahoo for authorization
    authorization_url, state = yahoo.authorization_url(YAHOO_AUTHORIZATION_BASE_URL)
    print(f'Please go to {authorization_url} and authorize access if required.')

    # Step 2: Get the authorization response from the redirect
    redirect_response = input('Paste the full redirect URL here: ')

    # Step 3: Fetch the access token
    token = yahoo.fetch_token(
        YAHOO_TOKEN_URL,
        authorization_response=redirect_response,
        client_secret=YAHOO_CLIENT_SECRET
    )

    # Save the token for future sessions
    save_token(token)
    print("Authentication successful!")
    return yahoo


def make_sample_request():
    """
    Makes a sample request to validate OAuth 2.0 login.
    """
    yahoo_session = yahoo_oauth_login()

    # Sample API request to get user's profile or basic account info
    response = yahoo_session.get('https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1')

    if response.status_code == 200:
        print("OAuth 2.0 login validated successfully!")
        pprint(response.text)
    else:
        print(f"Failed to validate OAuth 2.0 login. Status Code: {response.status_code}")
        print(response.text)


def make_api_request(uri):
    yahoo_session = yahoo_oauth_login()
    if not uri.startswith("/"):
        uri = f"/{uri}"
    response = yahoo_session.get(f"{YAHOO_API_BASE_URL}{uri}")
    response.raise_for_status()
    data = xmltodict.parse(response.text)
    return data


def get_user_info():
    return make_api_request(f"users;use_login=1/teams;is_available=1")

def get_users_lineups():
    user_info = get_user_info()
    team_keys = []
    roster_info = []
    teams = user_info['fantasy_content']['users']['user']['teams']['team']
    for team in teams:
        team_keys.append(team['team_key'])
    
    for team_key in team_keys:
        try:
            info = make_api_request(f"team/{team_key}/roster")
            is_editable = info["fantasy_content"]["team"]["roster"]["is_editable"]
            if is_editable == '1': # TODO: replace this with better logic to determin if this team is for the current year or not
                team_name = info["fantasy_content"]["team"]["name"]
                roster_info.append({
                    "team_key": team_key,
                    "team_name": team_name,
                    "players": info["fantasy_content"]["team"]["roster"]["players"]
                })
        except Exception as e:
            print(f"Could not get roster for team: [{team_key}]")
            pprint(e)

    return roster_info

def get_league_scoring_settings(team_key):
    """
    Fetches the league scoring settings for a given team.

    Args:
        team_key (str): The key of the team for which to fetch the scoring settings.

    Returns:
        dict: A dictionary containing the league scoring settings.
    """
    try:
        # Make the API request for the league's scoring settings
        league_key = team_key.split(".t.")[0]  # Extract the league key from the team key
        response = make_api_request(f"league/{league_key}/settings")

        # Extract relevant scoring settings
        scoring_settings = response["fantasy_content"]["league"]["settings"]["stat_modifiers"]
        return scoring_settings

    except Exception as e:
        print(f"Could not retrieve scoring settings for team: [{team_key}]")
        pprint(e)
        return None
