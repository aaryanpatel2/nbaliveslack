import os
import sys
import time
import argparse
from datetime import datetime
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# New Live Endpoints
from nba_api.live.nba.endpoints import scoreboard, boxscore

load_dotenv()

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

def get_recent_game_id(team_abbr):
    """Uses the CDN scoreboard to find a recently completed game."""
    try:
        # ScoreBoard() hits the CDN which is much more stable on GitHub Actions
        sb = scoreboard.ScoreBoard()
        data = sb.get_dict()
        games = data.get('scoreboard', {}).get('games', [])
        
        for game in games:
            home = game['homeTeam']['teamTricode']
            away = game['awayTeam']['teamTricode']
            if team_abbr in [home, away]:
                # gameStatus 3 means the game is finished
                if game['gameStatus'] == 3:
                    return game['gameId']
        return None
    except Exception as e:
        print(f"Scoreboard error: {e}")
        return None

def get_live_stats(game_id, team_abbr):
    """Fetches stats from the Live/CDN boxscore endpoint."""
    try:
        box = boxscore.BoxScore(game_id)
        data = box.get_dict()['game']
        
        is_home = data['homeTeam']['teamTricode'] == team_abbr
        team = data['homeTeam'] if is_home else data['awayTeam']
        opp = data['awayTeam'] if is_home else data['homeTeam']
        
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
        
        return {
            'matchup': f"{team['teamName']} vs {opp['teamName']}",
            'team_3p': team_3p,
            'opp_3p': opp_3p,
            'all_shooters': shooters
        }
    except Exception as e:
        print(f"Boxscore error: {e}")
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--team', default='OKC Thunder')
    args = parser.parse_args()
    
    team_abbr = TEAM_MAPPING.get(args.team, args.team)
    game_id = get_recent_game_id(team_abbr)
    
    if not game_id:
        print(f"No recent completed game found for {team_abbr}.")
        return

    # De-duplication check
    notified_file = 'last_notified_game.txt'
    if os.path.exists(notified_file):
        with open(notified_file, 'r') as f:
            if f.read().strip() == str(game_id):
                print("Already notified for this game.")
                return

    stats = get_live_stats(game_id, team_abbr)
    if not stats or not stats['all_shooters']:
        print("Stats not available yet.")
        return

    # Ranking logic
    made = sorted([s for s in stats['all_shooters'] if s['made'] > 0], key=lambda x: (-x['pct'], -x['made']))
    zero = sorted([s for s in stats['all_shooters'] if s['made'] == 0], key=lambda x: x['attempts'])
    ranked = made + zero
    top = ranked[0]

    # Message Construction
    msg = f"🏀 *{stats['matchup']}* 🏀\n\n"
    msg += f"*Team 3PT%:* {stats['team_3p']['pct']}% ({stats['team_3p']['made']}/{stats['team_3p']['att']})\n"
    msg += f"*Opponent ({stats['opp_3p']['name']}) 3PT%:* {stats['opp_3p']['pct']}% ({stats['opp_3p']['made']}/{stats['opp_3p']['att']})\n\n"
    msg += f"🏆 *Top 3PT Shooter:* {top['name']} — {top['made']}/{top['attempts']} ({top['pct']}%)\n\n"
    msg += f"📊 *All 3PT Shooters (ranked):*\n"
    for s in ranked:
        msg += f"• {s['name']}: {s['made']}/{s['attempts']} ({s['pct']}%)\n"

    send_slack_message(msg)
    with open(notified_file, 'w') as f: f.write(str(game_id))

if __name__ == "__main__":
    main()