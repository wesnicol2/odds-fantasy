# config.py

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

if not API_KEY:
    raise ValueError("API_KEY is not set. Please ensure it is set in the environment or the .env file.")
