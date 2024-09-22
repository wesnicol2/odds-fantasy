# config.py

import os
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# API configuration
API_KEY = os.getenv('API_KEY')
BASE_URL = 'https://api.the-odds-api.com/v4'
EVENTS_URL = f'{BASE_URL}/sports/americanfootball_nfl/events'

# Data directory for saving odds
DATA_DIR = './data'

if not API_KEY:
    raise ValueError("API_KEY is not set. Please ensure it is set in the environment or the .env file.")
