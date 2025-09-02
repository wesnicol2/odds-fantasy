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

# Position-Stat Configuration (define relevant stats for each position) - These stats should be in Odds API format
POSITION_STAT_CONFIG = {
    "QB": ["player_rush_yds", "player_rush_tds", "player_pass_yds", "player_pass_tds", "player_interceptions"],
    "RB": ["player_rush_yds", "player_rush_tds", "player_reception_yds", "player_reception_tds", "player_receptions"],
    "WR": ["player_rush_yds", "player_rush_tds", "player_reception_yds", "player_reception_tds", "player_receptions"],
    "TE": ["player_rush_yds", "player_rush_tds", "player_reception_yds", "player_reception_tds", "player_receptions"],
    "K": ["player_field_goals", "player_kicking_points", "player_pats"],  # Placeholder if needed later
    "DEF": [],  # Placeholder for defense stats
}

# This mapping holds a key = yahoo Stat name and value = corresponding odds api market
STAT_MARKET_MAPPING_YAHOO = {
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



# Sleeper API 
SLEEPER_ODDS_API_PLAYER_NAME_MAPPING = {
    "A.J. Brown": "AJ Brown"
}


# Mapping from Sleeper stat names to Odds API market names
STAT_MARKET_MAPPING_SLEEPER = {
    # Passing
    "player_pass_yds": "pass_yd",
    "player_pass_tds": "pass_td",
    "player_pass_interceptions": "pass_int",
    "player_pass_2pt": "pass_2pt",
    "player_pass_yds_bonus_300": "bonus_pass_yd_300",
    "player_pass_yds_bonus_400": "bonus_pass_yd_400",

    # Rushing
    "player_rush_yds": "rush_yd",
    "player_anytime_td": "rush_td",
    "player_rush_2pt": "rush_2pt",
    "player_rush_yds_bonus_100": "bonus_rush_yd_100",
    "player_rush_yds_bonus_200": "bonus_rush_yd_200",

    # Receiving
    "player_receptions": "rec",
    "player_reception_yds": "rec_yd",
    # "player_anytime_td": "rec_td", commented to keep rushing and receiving TDs combined
    "player_reception_2pt": "rec_2pt",
    "player_reception_yds_bonus_100": "bonus_rec_yd_100",
    "player_reception_yds_bonus_200": "bonus_rec_yd_200",

    # Fumbles
    "player_fumbles": "fum",
    "player_fumbles_lost": "fum_lost",

    # Kicking
    "player_fg_made_0_19": "fgm_0_19",
    "player_fg_made_20_29": "fgm_20_29",
    "player_fg_made_30_39": "fgm_30_39",
    "player_fg_made_40_49": "fgm_40_49",
    "player_fg_made_50_59": "fgm_50_59",
    "player_fg_made_60_plus": "fgm_60p",
    "player_fg_missed": "fgmiss",
    "player_fg_missed_0_19": "fgmiss_0_19",
    "player_fg_missed_20_29": "fgmiss_20_29",
    "player_fg_missed_30_39": "fgmiss_30_39",
    "player_fg_missed_40_49": "fgmiss_40_49",
    "player_fg_missed_50_59": "fgmiss_50_59",
    "player_fg_missed_60_plus": "fgmiss_60p",
    "player_xp_made": "xpm",
    "player_xp_missed": "xpmiss",

    # Defense/Special Teams
    "player_sacks": "sack",
    "player_def_interceptions": "int",
    "player_def_fumble_rec": "fum_rec",
    "player_def_fumble_rec_td": "fum_rec_td",
    "player_def_td": "def_td",
    "player_def_st_td": "def_st_td",
    "player_def_st_fum_rec": "def_st_fum_rec",
    "player_def_st_ff": "def_st_ff",
    "player_st_td": "st_td",
    "player_st_fum_rec": "st_fum_rec",
    "player_st_ff": "st_ff",
    "player_safeties": "safe",
    "player_blocked_kick": "blk_kick",
    "player_forced_fumble": "ff",

    # Points allowed (for D/ST)
    "player_pts_allow_0": "pts_allow_0",
    "player_pts_allow_1_6": "pts_allow_1_6",
    "player_pts_allow_7_13": "pts_allow_7_13",
    "player_pts_allow_14_20": "pts_allow_14_20",
    "player_pts_allow_21_27": "pts_allow_21_27",
    "player_pts_allow_28_34": "pts_allow_28_34",
    "player_pts_allow_35_plus": "pts_allow_35p",
}

SLEEPER_TO_ODDSAPI_TEAM = {
    "ARI": "Arizona Cardinals",
    "ATL": "Atlanta Falcons",
    "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers",
    "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals",
    "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos",
    "DET": "Detroit Lions",
    "GB":  "Green Bay Packers",
    "HOU": "Houston Texans",
    "IND": "Indianapolis Colts",
    "JAX": "Jacksonville Jaguars",
    "KC":  "Kansas City Chiefs",
    "LV":  "Las Vegas Raiders",
    "LAC": "Los Angeles Chargers",
    "LAR": "Los Angeles Rams",
    "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings",
    "NE":  "New England Patriots",
    "NO":  "New Orleans Saints",
    "NYG": "New York Giants",
    "NYJ": "New York Jets",
    "PHI": "Philadelphia Eagles",
    "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks",
    "SF":  "San Francisco 49ers",
    "TB":  "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans",
    "WAS": "Washington Commanders",
}