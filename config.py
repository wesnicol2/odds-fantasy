import os
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# API configuration for The Odds API
API_KEY = os.getenv('API_KEY')
BASE_URL = 'https://api.the-odds-api.com/v4'
EVENTS_URL = f'{BASE_URL}/sports/americanfootball_nfl/events'

# Data directory for saving various data
DATA_DIR = './data'

# Yahoo API OAuth 2.0 credentials
YAHOO_CLIENT_ID = os.getenv('YAHOO_CLIENT_ID')
YAHOO_CLIENT_SECRET = os.getenv('YAHOO_CLIENT_SECRET')
YAHOO_REDIRECT_URI = os.getenv('YAHOO_REDIRECT_URI')
YAHOO_AUTHORIZATION_BASE_URL = 'https://api.login.yahoo.com/oauth2/request_auth'
YAHOO_TOKEN_URL = 'https://api.login.yahoo.com/oauth2/get_token'
YAHOO_OAUTH_TOKEN_FILE = f'{DATA_DIR}/yahoo_token.json'  # File to save access and refresh tokens
YAHOO_API_BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"
YAHOO_LEAGUE_ID = os.getenv('YAHOO_LEAGUE_ID')

# Position-Stat Configuration (define relevant stats for each position)
POSITION_STAT_CONFIG = {
    "QB": ["player_pass_yds", "player_pass_tds", "player_rush_yds", "player_rush_tds", "player_interceptions"],
    "RB": ["player_rush_yds", "player_rush_tds", "player_reception_yds", "player_reception_tds"],
    "WR": ["player_reception_yds", "player_reception_tds"],
    "TE": ["player_reception_yds", "player_reception_tds"],
    "K": [],  # Placeholder if needed later
    "DEF": [],  # Placeholder for defense stats
}

# This mapping holds a key = yahoo Stat name and value = corresponding odds api market
STAT_MARKET_MAPPING = {
    "player_pass_yds": "player_pass_yds",
    "player_pass_tds": "player_pass_tds",
    "player_interceptions": "player_pass_interceptions",
    "player_rush_yds": "player_rush_yds",
    # Combine rushing and receiving touchdowns into "player_anytime_td"
    "player_rush_tds": "player_anytime_td",
    "player_reception_tds": "player_anytime_td",
    "player_reception_yds": "player_reception_yds",
}


# Mapping between player names on yahoo and odds api. 
# Left side is Yahoo, right side is Odds API
YAHOO_ODDS_API_PLAYER_NAME_MAPPING ={
    "A.J. Brown": "AJ Brown"
}
