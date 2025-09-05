from pprint import pprint
from collections import defaultdict
import datetime
from predicted_stats import predict_stats_for_player
import sleeper_api
import requests
import odds_api
from config import SLEEPER_ODDS_API_PLAYER_NAME_MAPPING, STAT_MARKET_MAPPING_SLEEPER

def calculate_fantasy_points(projected_stats, scoring_settings):
    """
    Calculate fantasy points for a player based on their projected stats and the league's scoring settings.

    Args:
        projected_stats (dict): A dictionary of the player's projected stats (e.g., passing yards, touchdowns).
        scoring_settings (dict): A dictionary of the league's scoring settings for different stat categories.

    Returns:
        float: The player's projected fantasy points.
    """
    fantasy_points = 0.0

    # Loop over each stat category in the projected stats
    for stat_key, stat_value in projected_stats.items():
        # Map the stat_key to the Yahoo stat_id using STAT_ID_MAPPING
        stat_id = STAT_MARKET_MAPPING_SLEEPER.get(stat_key)
        if not stat_id:
            continue  # If the stat_key isn't mapped, skip it

        # Find the corresponding stat_id in the league's scoring settings
        for stat, value in scoring_settings.items():
            if stat == stat_id:
                # Multiply the projected stat value by the league's scoring modifier
                modifier = float(value)
                fantasy_points += stat_value * modifier
                break  # Found the stat, no need to check further categories

    return fantasy_points


def print_rosters_with_projected_stats(username, season, use_saved_data=True):
    """
    Fetch and print the players along with their projected fantasy points and individual predicted stats in table format.
    Players are sorted by their predicted fantasy points in descending order.
    """
    try:
        roster = sleeper_api.get_user_sleeper_data(username, season)
        rosters = [roster] # TODO: In the future, enhance to get multiple rosters

        # Fetch odds for all games, either using saved data or fresh API data
        all_player_odds = odds_api.fetch_odds_for_all_games(rosters, use_saved_data=use_saved_data)
        
        # List to store player data for sorting later
        player_data_list = []
        all_stat_keys = set()  # To track all different stat keys

        # Loop through each roster
        for roster in rosters:

            # Get the league's scoring settings for the team
            league_settings = roster.get('scoring_rules')
            if not league_settings:
                continue

            # Loop through each player in the roster
            for player in roster["players"].values():
                # Use Odds API version of name from the beginning
                player_sleeper_name = player["name"]["full"]
                player_name = SLEEPER_ODDS_API_PLAYER_NAME_MAPPING.get(player_sleeper_name)
                if not player_name:
                    player_name = player_sleeper_name
                aggregated_player_odds = {}

                # Loop through all games' odds to find the player
                for game_id, game_odds in all_player_odds.items():
                    # Go through each bookmaker for the game
                    for bookmaker in game_odds["bookmakers"]:
                        bookmaker_key = bookmaker["key"]
                        # Check all markets for player odds
                        for market in bookmaker["markets"]:
                            for outcome in market["outcomes"]:
                                if "description" in outcome and outcome["description"] == player_name:
                                    if bookmaker_key not in aggregated_player_odds:
                                        aggregated_player_odds[bookmaker_key] = {}
                                    if market["key"] not in aggregated_player_odds[bookmaker_key]:
                                        aggregated_player_odds[bookmaker_key][market["key"]] = {
                                            "over": None,
                                            "under": None
                                        }

                                    # For simplicity, assume all odds are "Yes" (e.g., for anytime TD)
                                    # You can modify this logic to support "Over/Under" more explicitly
                                    aggregated_player_odds[bookmaker_key][market["key"]]["over"] = {
                                        "odds": outcome["price"],
                                        "point": outcome.get("point", 0)  # Use threshold if available, else 0
                                    }

                # If we found odds for the player, calculate projected stats and fantasy points
                if aggregated_player_odds:
                    projected_stats = predict_stats_for_player(aggregated_player_odds)
                    projected_fantasy_points = calculate_fantasy_points(projected_stats, league_settings)

                    # Track all unique stat keys for table columns
                    all_stat_keys.update(projected_stats.keys())

                    # Store player data in a list for sorting
                    player_data_list.append({
                        "player_name": player_name,
                        "projected_points": projected_fantasy_points,
                        "projected_stats": projected_stats,
                        "position": player.get("primary_position", "N/A")
                    })
                else:
                    # If no odds data, treat player as 0 projected points
                    player_data_list.append({
                        "player_name": player_name,
                        "projected_points": 0.0,
                        "projected_stats": {},
                        "position": player.get("primary_position", "N/A")
                    })

            print("All players in order of projected fantasy points:")
            print_all_player_projected_stats(player_data_list, all_stat_keys)


            print("Ideal lineup: ")
            print_ideal_lineup(player_data_list)
        

    except requests.exceptions.RequestException as e:
        print(f"ERROR when making API request: {e}")
        print(f"Response: {e.response.text}")
        print(f"URL Requested: {e.request.url}")


def print_all_player_projected_stats(player_data_list, all_stat_keys):
    # Sort the players by projected fantasy points (descending order)
        sorted_player_data = sorted(player_data_list, key=lambda x: x["projected_points"], reverse=True)

        # Convert all_stat_keys to a sorted list for table columns
        all_stat_keys = sorted(all_stat_keys)

        # Print the table header with dynamic columns for each stat
        header = f"{'Player Name':<20} | {'Fantasy Points':>15} | " + " | ".join([f"{stat:<20}" for stat in all_stat_keys])
        print(header)
        print("-" * len(header))

        # Print top players for each position. 1qb, 2 wr, 2 rb, 1 te, 1 flex (WR/RB/TE)
        # Print each player's data in table format
        for player_data in sorted_player_data:
            player_name = player_data['player_name']
            projected_points = player_data['projected_points']
            predicted_stats = player_data['projected_stats']

            # Prepare the row with player name, fantasy points, and predicted stats
            row = f"{player_name:<20} | {projected_points:>15.2f} | "
            row += " | ".join([f"{predicted_stats.get(stat, 0):<20.2f}" for stat in all_stat_keys])
            print(row)


def print_ideal_lineup(player_data_list):
    # Sort the players by projected fantasy points (descending order)
    sorted_player_data = sorted(player_data_list, key=lambda x: x["projected_points"], reverse=True)

    # --- Build starting lineup ----------------------------------------------------
    # Bucket players by position (use 'primary_position' if that's your key)
    buckets = defaultdict(list)
    for p in sorted_player_data:
        pos = p.get("position") or p.get("primary_position") or p.get("pos")
        p["_pos"] = pos  # normalize for printing
        if pos in ("QB", "RB", "WR", "TE"):
            buckets[pos].append(p)

    used_names = set()

    def take(pos: str, n: int):
        picks = []
        for p in buckets.get(pos, []):
            name = p["player_name"]
            if name not in used_names:
                picks.append(p)
                used_names.add(name)
                if len(picks) == n:
                    break
        return picks

    lineup = {
        "QB":   take("QB", 1),
        "WR":   take("WR", 2),
        "RB":   take("RB", 2),
        "TE":   take("TE", 1),
    }

    # FLEX = best remaining WR/RB/TE not already used
    flex_pool = []
    for pos in ("WR", "RB", "TE"):
        for p in buckets.get(pos, []):
            if p["player_name"] not in used_names:
                flex_pool.append(p)
    flex_pool.sort(key=lambda x: x["projected_points"], reverse=True)
    lineup["FLEX"] = flex_pool[:1]
    for p in lineup["FLEX"]:
        used_names.add(p["player_name"])

    # --- Print starting lineup ----------------------------------------------------
    print("\nSTARTING LINEUP")
    slot_header = f"{'Slot':<6} | {'Player Name':<20} | {'Pos':<3} | {'Fantasy Points':>15}"
    print(slot_header)
    print("-" * len(slot_header))

    def print_slot(slot: str, p: dict):
        print(f"{slot:<6} | {p['player_name']:<20} | {p['_pos']:<3} | {p['projected_points']:>15.2f}")

    for p in lineup["QB"]:   print_slot("QB",   p)
    for p in lineup["WR"]:   print_slot("WR",   p)
    for p in lineup["RB"]:   print_slot("RB",   p)
    for p in lineup["TE"]:   print_slot("TE",   p)
    for p in lineup["FLEX"]: print_slot("FLEX", p) 


def find_betting_opportunities_with_fanduel(all_player_odds):
    """
    Identifies betting opportunities where FanDuel offers better odds and/or better thresholds 
    compared to the average odds and thresholds from other bookmakers for the same player and market. 
    Sorts by the largest advantage for FanDuel.
    
    Args:
        all_player_odds (dict): Dictionary containing odds data for all games and markets.
    
    Returns:
        list: List of betting opportunities where FanDuel has better odds and thresholds compared 
        to the average odds and thresholds from other sportsbooks.
    """
    opportunities = []

    # Iterate over all games and bookmakers
    for game_id, game_odds in all_player_odds.items():
        fanduel_odds = None

        # First, find FanDuel's odds for this game
        for bookmaker in game_odds["bookmakers"]:
            if bookmaker["key"] == "fanduel":
                fanduel_odds = bookmaker["markets"]  # Get all markets for FanDuel
                break

        if not fanduel_odds:
            continue  # Skip this game if FanDuel is not available

        # Compare FanDuel odds with the average odds and thresholds from other bookmakers
        for fanduel_market in fanduel_odds:
            fanduel_market_key = fanduel_market["key"]
            fanduel_outcomes = fanduel_market["outcomes"]

            # Track total odds, thresholds, and count for each outcome to calculate the average
            average_data = {}

            # Collect odds from all other bookmakers
            for bookmaker in game_odds["bookmakers"]:
                if bookmaker["key"] == "fanduel":
                    continue  # Skip FanDuel for averaging

                for market in bookmaker["markets"]:
                    if market["key"] == fanduel_market_key:
                        for outcome in market["outcomes"]:
                            player_name = outcome["description"]
                            price = outcome["price"]
                            threshold = outcome.get("point", 0)

                            

                            # Initialize if not present
                            if player_name not in average_data:
                                average_data[player_name] = {
                                    "total_price": 0,
                                    "total_threshold": 0,
                                    "count": 0
                                }

                            # Add up odds and thresholds
                            average_data[player_name]["total_price"] += price
                            average_data[player_name]["total_threshold"] += threshold
                            average_data[player_name]["count"] += 1
                            if player_name == "Trayveon Williams":
                                print("breakpoint")

            # Now compare FanDuel's odds with the average odds and thresholds
            for fanduel_outcome in fanduel_outcomes:
                fanduel_player = fanduel_outcome["description"]
                fanduel_price = fanduel_outcome["price"]
                fanduel_threshold = fanduel_outcome.get("point", 0)

                # If we have average data for this player and market
                if fanduel_player in average_data:
                    avg_data = average_data[fanduel_player]
                    if avg_data["count"] > 0:
                        avg_price = avg_data["total_price"] / avg_data["count"]
                        avg_threshold = avg_data["total_threshold"] / avg_data["count"]

                        # Compare FanDuel's odds and threshold with the average
                        if fanduel_price > avg_price:
                            odds_factor = fanduel_price / avg_price
                            threshold_diff = fanduel_threshold - avg_threshold
                            opportunities.append({
                                "player": fanduel_player,
                                "market": fanduel_market_key,
                                "fanduel_odds": fanduel_price,
                                "fanduel_threshold": fanduel_threshold,
                                "average_odds": avg_price,
                                "average_threshold": avg_threshold,
                                "odds_factor": odds_factor,
                                "threshold_diff": threshold_diff,
                                "game_id": game_id
                            })

    # Sort the opportunities by the biggest odds difference, then by threshold difference (both descending)
    sorted_opportunities = sorted(opportunities, key=lambda x: (x["odds_factor"], x["threshold_diff"]), reverse=True)

    return sorted_opportunities


def print_betting_opportunities(opportunities):
    """
    Prints a list of betting opportunities where FanDuel has better odds and thresholds compared to other sportsbooks.

    Args:
        opportunities (list): The list of opportunities sorted by odds and threshold advantage for FanDuel.
    """
    print(f"{'Player':<20} | {'Market':<20} | {'FD Odds':<10} | {'FD Threshold':<15} | {'Avg Odds':<10} | {'Avg Threshold':<15} | {'Odds Factor':<10} | {'Thresh Diff':<12}")
    print("-" * 110)
    
    for opp in opportunities:

        print(f"{opp['player']:<20} | {opp['market']:<20} | {opp['fanduel_odds']:<10} | {opp['fanduel_threshold']:<15} | {round(opp['average_odds'], 2):<10} | {round(opp['average_threshold'], 2):<15} | {round(opp['odds_factor'], 2):<10} | {round(opp['threshold_diff'], 2):<12}")

def print_defense_possiblities(username, season, use_saved_data=True):
    """
    Fetch and print possible defenses for the user's roster.
    """
    import datetime
    try:
        # Get all rosters from Sleeper
        roster = sleeper_api.get_user_sleeper_data(username, season)
        rosters = [roster] # TODO: In the future, enhance to get multiple rosters

        # Define week windows
        today = datetime.datetime.now()
        days_until_thursday = (3 - today.weekday()) % 7
        this_week_start = today + datetime.timedelta(days=days_until_thursday)
        this_week_end = this_week_start + datetime.timedelta(days=4)  # Monday
        next_week_start = this_week_start + datetime.timedelta(days=7)
        next_week_end = next_week_start + datetime.timedelta(days=4)

        # Loop through each roster
        for roster in rosters:
            defenses = sleeper_api.get_available_defenses(username=username, season=season)
            defense_names = [
                f"{d.get('first_name','').strip()} {d.get('last_name','').strip()}".strip()
                for d in defenses.values()
            ]
            for p in roster.get("players", {}).values():
                if p.get("primary_position") == "DEF":
                    name = p.get("editorial_team_full_name")
                    if name:
                        defense_names.append(name)
            seen = set()
            defense_names = [x for x in defense_names if not (x in seen or seen.add(x))]

            # Group defenses by week window
            this_week_defenses = []
            next_week_defenses = []
            for defense in defense_names:
                all_game_data = odds_api.get_defensive_odds_for_team(team_name=defense, use_saved_data=use_saved_data)
                if not all_game_data:
                    continue
                for game_id, game_data in all_game_data.items():
                    commence_time_str = game_data.get("commence_time")
                    if not commence_time_str:
                        continue
                    # Parse commence_time (assume ISO8601 or unix timestamp)
                    try:
                        if isinstance(commence_time_str, (int, float)):
                            commence_time = datetime.datetime.fromtimestamp(commence_time_str)
                        else:
                            commence_time = datetime.datetime.fromisoformat(commence_time_str.replace("Z", ""))
                    except Exception:
                        continue

                    # Get opposing team name
                    if game_data.get("home_team") == defense:
                        opposing_team_name = game_data.get("away_team", "N/A")
                    else:
                        opposing_team_name = game_data.get("home_team", "N/A")

                    # Calculate opponent implied total
                    implied_total_count = 0
                    total_implied_total = 0
                    for bookmaker in game_data.get("bookmakers", []):
                        for market in bookmaker.get("markets", []):
                            if market["key"] == "spreads":
                                for outcome in market.get("outcomes", []):
                                    if outcome["name"] == opposing_team_name:
                                        spread = outcome.get("point", 0)
                            if market["key"] == "totals":
                                for outcome in market.get("outcomes", []):
                                    if outcome["name"] == "Over":
                                        total = outcome.get("point", 0)
                        opponent_implied_total = implied_total(game_total=total, team_spread=spread)
                        implied_total_count += 1
                        total_implied_total += opponent_implied_total
                    average_implied_total = total_implied_total / implied_total_count if implied_total_count else None

                    defense_data = {
                        "defense": defense,
                        "opposing_team": opposing_team_name,
                        "average_implied_total": average_implied_total,
                        "implied_total_count": implied_total_count,
                        "game_date": commence_time.strftime('%Y-%m-%d %a'),
                    }

                    if this_week_start <= commence_time <= this_week_end:
                        this_week_defenses.append(defense_data)
                    elif next_week_start <= commence_time <= next_week_end:
                        next_week_defenses.append(defense_data)

            # Print tables
            print(f"Defenses Playing This Week ({this_week_start.strftime('%b %d')}–{this_week_end.strftime('%b %d, %Y')}):")
            print_defense_table(this_week_defenses, decimals=2)
            print("")
            print(f"Defenses Playing Next Week ({next_week_start.strftime('%b %d')}–{next_week_end.strftime('%b %d, %Y')}):")
            print_defense_table(next_week_defenses, decimals=2)

    except requests.exceptions.RequestException as e:
        print(f"ERROR when making API request: {e}")
        print(f"Response: {e.response.text}")
        print(f"URL Requested: {e.request.url}")


def implied_total(game_total, team_spread):
    return game_total/2 - team_spread/2

def print_defense_table(all_defense_data, decimals=2):
    headers = ("Defense", "Opponent", "Opp Avg Implied", "# Books", "Proj FPts")
    rows = []

    def fmt_num(x):
        if isinstance(x, (int, float)):
            return f"{x:.{decimals}f}" if isinstance(x, float) else f"{x:d}"
        return "—"

    for d in sorted(all_defense_data, key=lambda x: x["average_implied_total"]):
        rows.append((
            d.get("defense", ""),
            d.get("opposing_team", ""),
            fmt_num(d.get("average_implied_total")),
            fmt_num(d.get("implied_total_count")),
            d.get("projected_fantasy_points", "TBD"),
        ))

    if not rows:
        print("No defenses found for this week.")
        return

    # compute column widths (headers + rows)
    cols = list(zip(*([headers] + rows)))
    widths = [max(len(str(cell)) for cell in col) for col in cols]

    # left align text cols (0,1), right align numeric-ish cols (2,3,4)
    fmt = f"{{:<{widths[0]}}}  {{:<{widths[1]}}}  {{:>{widths[2]}}}  {{:>{widths[3]}}}  {{:>{widths[4]}}}"
    sep = "  ".join("─" * w for w in widths)

    print(fmt.format(*headers))
    print(sep)
    for r in rows:
        print(fmt.format(*r))


if __name__ == "__main__":
    # Set `use_saved_data=False` to force fetching fresh odds data
    # print_rosters_with_projected_stats(username="wesnicol", season="2025", use_saved_data=False)

    print_defense_possiblities(username="wesnicol", season="2025", use_saved_data=False)
    
    
    # Assuming 'all_player_odds' contains the odds data for all games and markets
    # all_player_odds = odds_api.fetch_odds_for_all_games(rosters=None, use_saved_data=False)
    
    # # Find the betting opportunities where FanDuel offers better odds and thresholds
    # fanduel_opportunities = find_betting_opportunities_with_fanduel(all_player_odds)
    
    # # Print the betting opportunities
    # print_betting_opportunities(fanduel_opportunities)

