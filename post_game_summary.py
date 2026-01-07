import os
import sys
from dotenv import load_dotenv
from nba_api.stats.endpoints import leaguegamefinder
from nba_api.live.nba.endpoints import boxscore as live_boxscore
from datetime import datetime, timedelta
import argparse

load_dotenv()

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

slack_token = os.getenv("SLACK_BOT_TOKEN")
slack_user = os.getenv("SLACK_USER_ID")

client = WebClient(token=slack_token)

# Team name to abbreviation mapping
TEAM_MAPPING = {
    'OKC Thunder': 'OKC',
    'Oklahoma City Thunder': 'OKC',
    'Lakers': 'LAL',
    'Warriors': 'GSW',
    'Celtics': 'BOS',
    'Heat': 'MIA',
    'Nets': 'BKN',
    'Knicks': 'NYK',
    'Sixers': 'PHI',
    'Bucks': 'MIL',
    'Bulls': 'CHI',
    'Cavaliers': 'CLE',
    'Pistons': 'DET',
    'Pacers': 'IND',
    'Hawks': 'ATL',
    'Hornets': 'CHA',
    'Magic': 'ORL',
    'Wizards': 'WAS',
    'Nuggets': 'DEN',
    'Timberwolves': 'MIN',
    'Thunder': 'OKC',
    'Trail Blazers': 'POR',
    'Jazz': 'UTA',
    'Suns': 'PHX',
    'Clippers': 'LAC',
    'Kings': 'SAC',
    'Mavericks': 'DAL',
    'Rockets': 'HOU',
    'Grizzlies': 'MEM',
    'Pelicans': 'NOP',
    'Spurs': 'SAS',
    'Raptors': 'TOR',
}

# Stat type configurations
STAT_CONFIGS = {
    '3pt': {
        'name': '3-Point',
        'made_col': 'FG3M',
        'attempt_col': 'FG3A',
        'emoji': '🏀',
        'description': 'three-pointers'
    },
    'fg': {
        'name': 'Field Goal',
        'made_col': 'FGM',
        'attempt_col': 'FGA',
        'emoji': '🎯',
        'description': 'field goals'
    },
    'ft': {
        'name': 'Free Throw',
        'made_col': 'FTM',
        'attempt_col': 'FTA',
        'emoji': '🎯',
        'description': 'free throws'
    },
}

def send_slack_message(text):
    """Send a message to Slack."""
    try:
        response = client.chat_postMessage(
            channel=slack_user,
            text=text
        )
        print(f"Message sent successfully: {text}")
    except SlackApiError as e:
        print(f"Error sending message: {e.response['error']}")
        sys.exit(1)

def get_team_abbreviation(team_name):
    """Convert team name to abbreviation."""
    return TEAM_MAPPING.get(team_name, team_name)

def get_recent_game(team_abbr, days_back=1):
    """Get the most recent completed game for a team."""
    try:
        # Search for games in the last few days
        date_to = datetime.now()
        date_from = date_to - timedelta(days=days_back)
        
        print(f"Searching for games between {date_from.strftime('%m/%d/%Y')} and {date_to.strftime('%m/%d/%Y')}")
        
        gamefinder = leaguegamefinder.LeagueGameFinder(
            team_id_nullable=None,
            date_from_nullable=date_from.strftime('%m/%d/%Y'),
            date_to_nullable=date_to.strftime('%m/%d/%Y')
        )
        
        games = gamefinder.get_data_frames()[0]
        
        print(f"Total games found: {len(games)}")
        
        # Filter for the specific team
        team_games = games[games['TEAM_ABBREVIATION'] == team_abbr]
        
        print(f"Games for {team_abbr}: {len(team_games)}")
        if not team_games.empty:
            print(f"Most recent game details:")
            print(f"  Game ID: {team_games.iloc[0]['GAME_ID']}")
            print(f"  Date: {team_games.iloc[0]['GAME_DATE']}")
            print(f"  Matchup: {team_games.iloc[0]['MATCHUP']}")
        
        if team_games.empty:
            return None
        
        # Get the most recent game
        most_recent = team_games.iloc[0]
        return most_recent['GAME_ID']
    
    except Exception as e:
        print(f"Error finding recent game: {e}")
        return None

def get_game_stats(game_id, team_abbr, stat_type='3pt'):
    """Get player statistics for a specific game and stat type."""
    try:
        print(f"Fetching live boxscore for game {game_id}, team {team_abbr}")
        box = live_boxscore.BoxScore(game_id)
        data = box.game.get_dict()
        # Find team info
        teams = data['homeTeam'], data['awayTeam']
        team = next(t for t in teams if t['teamTricode'] == team_abbr)
        opp = next(t for t in teams if t['teamTricode'] != team_abbr)
        # Team 3pt stats
        team_3pm = team['statistics']['threePointersMade']
        team_3pa = team['statistics']['threePointersAttempted']
        team_3p_pct = round(100 * team_3pm / team_3pa, 1) if team_3pa > 0 else 0.0
        opp_3pm = opp['statistics']['threePointersMade']
        opp_3pa = opp['statistics']['threePointersAttempted']
        opp_3p_pct = round(100 * opp_3pm / opp_3pa, 1) if opp_3pa > 0 else 0.0
        # Player stats
        players = team['players']
        shooters = [
            {
                'name': p['name'],
                'made': p['statistics']['threePointersMade'],
                'attempts': p['statistics']['threePointersAttempted'],
                'pct': round(100 * p['statistics']['threePointersMade'] / p['statistics']['threePointersAttempted'], 1) if p['statistics']['threePointersAttempted'] > 0 else 0.0
            }
            for p in players if p['statistics']['threePointersAttempted'] > 0
        ]
        if not shooters:
            return None, STAT_CONFIGS['3pt']
        shooters = sorted(shooters, key=lambda x: (-x['pct'], -x['made']))
        top_shooter = shooters[0]
        return {
            'matchup': f"{team['teamName']} vs {opp['teamName']}",
            'team_3p': {'pct': team_3p_pct, 'made': team_3pm, 'att': team_3pa},
            'opp_3p': {'pct': opp_3p_pct, 'made': opp_3pm, 'att': opp_3pa, 'name': opp['teamName']},
            'top_shooter': top_shooter,
            'all_shooters': shooters
        }, STAT_CONFIGS['3pt']
    except Exception as e:
        print(f"Error getting game stats: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def format_game_summary(stats, stat_config, team_name):
    """Format the game summary message."""
    if not stats or not stat_config:
        desc = stat_config['description'] if stat_config else 'shots'
        return f"No {desc} attempted by {team_name} in their recent game."
    
    top = stats['top_shooter']
    emoji = stat_config['emoji']
    stat_name = stat_config['name']
    
    message = f"{emoji} *{team_name} - Post-Game {stat_name} Summary* {emoji}\n\n"
    message += f"🏆 *Top Performer:* {top['name']}\n"
    message += f"   {top['made']}/{top['attempts']} ({top['pct']}%)\n\n"
    message += f"📊 *All Players:*\n"
    
    for shooter in stats['all_shooters']:
        message += f"• {shooter['name']}: {shooter['made']}/{shooter['attempts']} ({shooter['pct']}%)\n"
    
    return message

def main():
    """Main function to generate and send post-game summary."""
    parser = argparse.ArgumentParser(description='Send NBA post-game stat summary to Slack')
    parser.add_argument('--team', default='OKC Thunder', help='Team name (default: OKC Thunder)')
    parser.add_argument('--stat', default='3pt', choices=['3pt', 'fg', 'ft'], 
                        help='Stat type to track (default: 3pt)')
    parser.add_argument('--days-back', type=int, default=1, 
                        help='Number of days to look back for games (default: 1)')
    
    args = parser.parse_args()
    
    team_abbr = get_team_abbreviation(args.team)
    
    print(f"Looking for recent {args.team} ({team_abbr}) game...")
    
    # Find the most recent game with available boxscore stats
    date_to = datetime.now()
    date_from = date_to - timedelta(days=args.days_back)
    gamefinder = leaguegamefinder.LeagueGameFinder(
        team_id_nullable=None,
        date_from_nullable=date_from.strftime('%m/%d/%Y'),
        date_to_nullable=date_to.strftime('%m/%d/%Y')
    )
    games = gamefinder.get_data_frames()[0]
    team_games = games[games['TEAM_ABBREVIATION'] == team_abbr]
    if team_games.empty:
        message = f"No recent game found for {args.team} in the last {args.days_back} day(s)."
        print(message)
        send_slack_message(message)
        return

    # Read last notified game ID
    notified_file = os.path.join(os.path.dirname(__file__), 'last_notified_game.txt')
    last_notified_game = None
    if os.path.exists(notified_file):
        with open(notified_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    last_notified_game = line
                    break

    # Only check the most recent game
    found_stats = False
    game_id = team_games.iloc[0]['GAME_ID']
    print(f"Checking most recent game: {game_id} ({team_games.iloc[0]['GAME_DATE']}, {team_games.iloc[0]['MATCHUP']})")
    
    # Skip if already notified
    if last_notified_game == str(game_id):
        print(f"Already notified for game {game_id}, skipping.")
        return
    
    stats, stat_config = get_game_stats(game_id, team_abbr, args.stat)
    if stats and stats['all_shooters']:
        found_stats = True
        print(f"Found stats for game {game_id}")
    
    if not found_stats:
        message = f"No boxscore stats available for {args.team} in the last {args.days_back} day(s). NBA API may be lagging."
        print(message)
        return

    # Format Slack message as requested
    matchup = stats['matchup']
    team_3p = stats['team_3p']
    opp_3p = stats['opp_3p']
    shooters = stats['all_shooters']
    # Separate shooters with at least 1 made from those with 0 made
    made_shooters = [s for s in shooters if s['made'] > 0]
    zero_made_shooters = [s for s in shooters if s['made'] == 0]
    # Sort made shooters by pct desc, then made desc
    made_shooters = sorted(made_shooters, key=lambda x: (-x['pct'], -x['made']))
    # Sort zero-made shooters by attempts ascending (lowest first)
    zero_made_shooters = sorted(zero_made_shooters, key=lambda x: x['attempts'])
    # Combine
    ranked_shooters = made_shooters + zero_made_shooters
    top = made_shooters[0] if made_shooters else ranked_shooters[0]
    emoji = stat_config['emoji']
    message = f"{emoji} *{matchup}* {emoji}\n\n"
    message += f"*Team 3PT%:* {team_3p['pct']}% ({team_3p['made']}/{team_3p['att']})\n"
    message += f"*Opponent ({opp_3p['name']}) 3PT%:* {opp_3p['pct']}% ({opp_3p['made']}/{opp_3p['att']})\n\n"
    message += f"🏆 *Top 3PT Shooter:* {top['name']} — {top['made']}/{top['attempts']} ({top['pct']}%)\n\n"
    message += f"📊 *All 3PT Shooters (ranked):*\n"
    for shooter in ranked_shooters:
        message += f"• {shooter['name']}: {shooter['made']}/{shooter['attempts']} ({shooter['pct']}%)\n"
    send_slack_message(message)
    # Update last notified game file
    with open(notified_file, 'w') as f:
        f.write(str(game_id) + '\n')

if __name__ == "__main__":
    main()
