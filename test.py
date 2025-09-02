
from sleeper_api import get_user_id, get_user_leagues, get_league_rosters, get_players

# Replace with your Sleeper username and season
your_username = "wesnicol"
season = "2025"

try:
    user_id = get_user_id(your_username)
    leagues = get_user_leagues(user_id, season)
    if not leagues:
        print(f"No leagues found for user {your_username} in {season}.")
        exit()
    league_id = leagues[0]['league_id']
    rosters = get_league_rosters(league_id)
    players_metadata = get_players()


    print(f"\nYour roster in league '{leagues[0]['name']}' ({league_id}):\n")
    my_roster = None
    for roster in rosters:
        if roster.get('owner_id') == user_id:
            my_roster = roster
            break
    if not my_roster:
        print("Could not find your roster in this league.")
        exit()

    starters = my_roster.get('starters', [])
    all_players = my_roster.get('players', [])

    print("Starters:")
    for pid in starters:
        pdata = players_metadata.get(pid, {})
        name = pdata.get('full_name', pid)
        pos = pdata.get('position', 'N/A')
        print(f"  - {name} ({pos})")

    print("Bench:")
    for pid in set(all_players) - set(starters):
        pdata = players_metadata.get(pid, {})
        name = pdata.get('full_name', pid)
        pos = pdata.get('position', 'N/A')
        print(f"  - {name} ({pos})")

    # Print scoring rules
    print("\nScoring Rules:")
    scoring_settings = leagues[0].get('scoring_settings', {})
    for rule, value in scoring_settings.items():
        print(f"  {rule}: {value}")

except Exception as e:
    print(f"Error: {e}")
