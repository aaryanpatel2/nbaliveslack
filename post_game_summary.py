import os
import sys
import time
import argparse
import json
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import requests

# New Live Endpoints
from nba_api.live.nba.endpoints import scoreboard, boxscore

load_dotenv()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
}

PAGE_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
}

# Configuration & Mappings
slack_token = os.getenv("SLACK_BOT_TOKEN")
slack_user = os.getenv("SLACK_USER_ID")
client = WebClient(token=slack_token)

TEAM_MAPPING = {
    'OKC Thunder': 'OKC', 'Lakers': 'LAL', 'Warriors': 'GSW', 'Celtics': 'BOS',
    'Heat': 'MIA', 'Nets': 'BKN', 'Knicks': 'NYK', 'Sixers': 'PHI',
    'Bucks': 'MIL', 'Bulls': 'CHI', 'Cavaliers': 'CLE', 'Pistons': 'DET',
    'Pacers': 'IND', 'Hawks': 'ATL', 'Hornets': 'CHA', 'Magic': 'ORL',
    'Wizards': 'WAS', 'Nuggets': 'DEN', 'Timberwolves': 'MIN', 'Thunder': 'OKC',
    'Trail Blazers': 'POR', 'Jazz': 'UTA', 'Suns': 'PHX', 'Clippers': 'LAC',
    'Kings': 'SAC', 'Mavericks': 'DAL', 'Rockets': 'HOU', 'Grizzlies': 'MEM',
    'Pelicans': 'NOP', 'Spurs': 'SAS', 'Raptors': 'TOR'
}

def send_slack_message(text):
    try:
        client.chat_postMessage(channel=slack_user, text=text)
        print(f"Slack message sent.")
    except SlackApiError as e:
        print(f"Slack error: {e.response['error']}")


def get_game_cards_for_date(game_date):
    """Fetches all game cards for a specific NBA games page date."""
    url = f"https://www.nba.com/games?date={game_date}"
    response = requests.get(url, headers=PAGE_HEADERS, timeout=20)
    response.raise_for_status()

    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', response.text, re.S)
    if not match:
        return []

    data = json.loads(match.group(1))
    page_props = data.get('props', {}).get('pageProps', {})
    game_feed = page_props.get('gameCardFeed', {})
    modules = game_feed.get('modules', [])

    cards = []
    for module in modules:
        for card in module.get('cards', []):
            card_data = card.get('cardData', {})
            if isinstance(card_data, dict) and card_data.get('gameId'):
                cards.append(card_data)

    return cards

def get_recent_game_id(team_abbr, days_back=1):
    """Finds the most recent completed game for a team across the requested date window."""
    return get_recent_game_id_for_days(team_abbr, days_back)


def get_recent_game_id_for_days(team_abbr, days_back):
    """Searches today's games page and prior days for the most recent completed game."""
    max_days_back = max(0, days_back)
    for offset in range(0, max_days_back + 1):
        game_date = datetime.now().date() - timedelta(days=offset)
        game_date_str = game_date.isoformat()
        try:
            print(f"Fetching NBA games page for {game_date_str}...")
            start_time = time.time()
            cards = get_game_cards_for_date(game_date_str)
            elapsed = time.time() - start_time
            print(f"Games page fetched in {elapsed:.2f}s")
            print(f"Found {len(cards)} game card(s) for {game_date_str}")

            for game in cards:
                home = game.get('homeTeam', {}).get('teamTricode')
                away = game.get('awayTeam', {}).get('teamTricode')
                if team_abbr in [home, away]:
                    game_status = game.get('gameStatus')
                    game_id = game.get('gameId')
                    print(f"Found {team_abbr} game: {game_id} (status={game_status})")
                    if game_status == 3:
                        print(f"Game {game_id} is completed")
                        return game_id
                    print(f"Game {game_id} not yet complete (status={game_status})")
        except Exception as e:
            print(f"Lookup for {game_date_str} failed: {e}")
            import traceback
            traceback.print_exc()

    print(f"No completed games found for {team_abbr}")
    return None

def get_live_stats(game_id, team_abbr):
    """Fetches stats from the Live/CDN boxscore endpoint."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                wait_time = 5 * (attempt + 1)
                print(f"Retry attempt {attempt + 1}/{max_retries} after {wait_time}s delay...")
                time.sleep(wait_time)
            
            print(f"Fetching boxscore for game {game_id} from CDN...")
            start_time = time.time()
            
            box = boxscore.BoxScore(game_id, headers=HEADERS)
            data = box.get_dict()['game']
            
            elapsed = time.time() - start_time
            print(f"Boxscore fetched in {elapsed:.2f}s")
            
            is_home = data['homeTeam']['teamTricode'] == team_abbr
            team = data['homeTeam'] if is_home else data['awayTeam']
            opp = data['awayTeam'] if is_home else data['homeTeam']
            
            print(f"Processing stats for {team['teamName']} vs {opp['teamName']}")
            
            # Team Stats
            team_3p = {
                'made': team['statistics']['threePointersMade'],
                'att': team['statistics']['threePointersAttempted'],
                'pct': round(100 * team['statistics']['threePointersMade'] / team['statistics']['threePointersAttempted'], 1) if team['statistics']['threePointersAttempted'] > 0 else 0
            }
            opp_3p = {
                'name': opp['teamName'],
                'made': opp['statistics']['threePointersMade'],
                'att': opp['statistics']['threePointersAttempted'],
                'pct': round(100 * opp['statistics']['threePointersMade'] / opp['statistics']['threePointersAttempted'], 1) if opp['statistics']['threePointersAttempted'] > 0 else 0
            }
            
            # Player Stats
            shooters = []
            for p in team['players']:
                s = p['statistics']
                if s['threePointersAttempted'] > 0:
                    shooters.append({
                        'name': p['name'],
                        'made': s['threePointersMade'],
                        'attempts': s['threePointersAttempted'],
                        'pct': round(100 * s['threePointersMade'] / s['threePointersAttempted'], 1)
                    })
            
            print(f"Found {len(shooters)} players with 3PT attempts")
            
            return {
                'matchup': f"{team['teamName']} vs {opp['teamName']}",
                'team_3p': team_3p,
                'opp_3p': opp_3p,
                'all_shooters': shooters
            }
            
        except Exception as e:
            print(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
            import traceback
            traceback.print_exc()
            if attempt == max_retries - 1:
                print(f"All retries exhausted for boxscore")
                return None
    
    return None

def main():
    parser = argparse.ArgumentParser(description='Send NBA post-game stat summary to Slack')
    # Add all arguments that GitHub Action needs
    parser.add_argument('--team', default='OKC Thunder', help='Team name')
    parser.add_argument('--stat', default='3pt', choices=['3pt', 'fg', 'ft'], help='Stat type')
    parser.add_argument('--days-back', type=int, default=1, help='Days to look back')
    
    args = parser.parse_args()
    
    team_abbr = TEAM_MAPPING.get(args.team, args.team)
    
    # Use the scoreboard to find the game
    print(f"Looking for recent {args.team} ({team_abbr}) game...")
    game_id = get_recent_game_id(team_abbr, args.days_back)
    
    if not game_id:
        print(f"No recent completed game found for {team_abbr} in today's scoreboard.")
        return

    # De-duplication check
    notified_file = os.path.join(os.path.dirname(__file__), 'last_notified_game.txt')
    if os.path.exists(notified_file):
        with open(notified_file, 'r') as f:
            if f.read().strip() == str(game_id):
                print(f"Already notified for game {game_id}, skipping.")
                return

    # Fetch stats
    stats = get_live_stats(game_id, team_abbr)
    if not stats or not stats['all_shooters']:
        print(f"Stats not available for game {game_id} yet.")
        return

    # Ranking logic
    shooters = stats['all_shooters']
    made_shooters = sorted([s for s in shooters if s['made'] > 0], key=lambda x: (-x['pct'], -x['made']))
    zero_made_shooters = sorted([s for s in shooters if s['made'] == 0], key=lambda x: x['attempts'])
    ranked_shooters = made_shooters + zero_made_shooters
    top = ranked_shooters[0]

    # Format and Send
    message = f"🏀 *{stats['matchup']}* 🏀\n\n"
    message += f"*Team 3PT%:* {stats['team_3p']['pct']}% ({stats['team_3p']['made']}/{stats['team_3p']['att']})\n"
    message += f"*Opponent ({stats['opp_3p']['name']}) 3PT%:* {stats['opp_3p']['pct']}% ({stats['opp_3p']['made']}/{stats['opp_3p']['att']})\n\n"
    message += f"🏆 *Top 3PT Shooter:* {top['name']} — {top['made']}/{top['attempts']} ({top['pct']}%)\n\n"
    message += f"📊 *All 3PT Shooters (ranked):*\n"
    for s in ranked_shooters:
        message += f"• {s['name']}: {s['made']}/{s['attempts']} ({s['pct']}%)\n"

    send_slack_message(message)

    # Save progress
    with open(notified_file, 'w') as f:
        f.write(str(game_id))

if __name__ == "__main__":
    main()
