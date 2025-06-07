import os
from dotenv import load_dotenv
from nba_api.live.nba.endpoints import scoreboard
from nba_api.stats.endpoints import scoreboardv2
from nba_api.live.nba.endpoints import playbyplay
from datetime import datetime, timezone
import time
import re

load_dotenv()

import logging
logging.basicConfig(level=logging.DEBUG)

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

slack_token = os.getenv("SLACK_BOT_TOKEN")
slack_user = os.getenv("SLACK_USER_ID")

client = WebClient(token=slack_token)

def message(play):
    try:
        response = client.chat_postMessage(
            channel=slack_user,
            text=play
        )
    except SlackApiError as e:
        # You will get a SlackApiError if "ok" is False
        assert e.response["error"]    # str like 'invalid_auth', 'channel_not_found'

# --- TEST CONFIGURATION ---
TEST_MODE = False
TEST_PAST_GAME_ID = '0022401196'
TEST_START_TIME = datetime(2025, 6, 2, 20, 0, 0, tzinfo=timezone.utc)
# --- TEST CONFIGURATION ---

def get_games_today():
    """Gets the games scheduled for today."""
    if TEST_MODE:
        print("--- RUNNING IN TEST MODE ---")
        return [{'game_id': TEST_PAST_GAME_ID, 'start_time_utc': TEST_START_TIME}]
    else:
        today_str = datetime.now().strftime('%m/%d/%Y')
        score = scoreboardv2.ScoreboardV2(game_date=today_str)
        games_today_data = score.get_normalized_dict()['GameHeader']
        games = []
        for game in games_today_data:
            game_id = game['GAME_ID']
            est_time_str = game['GAME_DATE_EST']
            start_time_est = datetime.fromisoformat(est_time_str)
            start_time_local = start_time_est.astimezone()  # Converts to local time
            games.append({'game_id': game_id, 'start_time_utc': start_time_est, 'start_time_local': start_time_local})
        return games

def get_live_play_by_play(game_id, use_normalized=True):
    """
    Fetches live play-by-play data for a given game ID.
    Can return data in normalized or regular format.
    """
    try:
        pbp = playbyplay.PlayByPlay(game_id)
        if use_normalized:
            plays = pbp.get_dict()['game']['actions']
            return plays
    except Exception as e:
        print(f"Error fetching play-by-play for game {game_id}: {e}")
        return None

def is_game_live(game_id):
    """Checks if a game is currently live."""
    if TEST_MODE and game_id == TEST_PAST_GAME_ID:
        return True  # In test mode, the past game is always "live"
    else:
        score = scoreboard.ScoreBoard()
        games = score.get_dict()['scoreboard']['games']
        for game in games:
            # gameStatus 3 means finished
            if game['gameId'] == game_id and game['gameStatus'] != 3:
                return True
        return False

def is_game_over(game_id):
    """Checks if a game is over."""
    # In test mode, we don't want the game to end prematurely
    if TEST_MODE and game_id == TEST_PAST_GAME_ID:
        return False
    else:
        score = scoreboard.ScoreBoard()
        games = score.get_dict()['scoreboard']['games']
        for game in games:
            # gameStatus 3 means finished
            if game['gameId'] == game_id and game['gameStatus'] == 3:
                return True
        return False

def monitor_games(games_today):
    """
    Monitors play-by-play for today's games using the normalized format.
    Tracks last seen event to only print new plays.
    """
    monitored_games = {} # Stores {'game_id': {'last_play_id': <int>}}
    
    # Initialize monitored_games with games that are expected to be live soon
    # or are already live. This loop ensures we start monitoring as games begin.
    # The outer while loop condition also helps ensure we keep checking for new games
    # to start if they are scheduled for today.
    
    # Loop as long as there are games being actively monitored
    # OR there are still games in today's schedule that haven't started monitoring yet
    # and are potentially live (or about to be live, though is_game_live handles actual live check)
    while monitored_games or any(game['game_id'] not in monitored_games for game in games_today):
        # Check for new games to start monitoring
        for game in games_today:
            game_id = game['game_id']
            if game_id not in monitored_games:
                if is_game_live(game_id): # Only start monitoring if the game is actually live
                    print(f"Starting to monitor play-by-play for game {game_id}...")
                    monitored_games[game_id] = {'last_play_id': -1} # Initialize with -1 to get all plays initially

        games_to_remove = []
        # Iterate through games currently being monitored
        for game_id, tracking in monitored_games.items():
            if is_game_live(game_id):
                # Fetch play-by-play data in normalized format
                pbp_data = get_live_play_by_play(game_id, use_normalized=True)
                if pbp_data:
                    # Sort plays by actionNumber to ensure correct order for tracking in scoreboardv2
                    pbp_data.sort(key=lambda x: x.get('actionNumber', 0))
                    
                    new_plays_found = False
                    for play in pbp_data:
                        print(play)
                        action_num = play.get('actionNumber', 0)
                        # Only process plays that are newer than the last seen play
                        if action_num > tracking['last_play_id']:
                            if (
                                play.get("actionType") == "3pt"
                                and play.get("shotResult") == "Made"
                                and play.get("isFieldGoal") == 1
                                and play.get('teamTricode') == "OKC"
                            ):
                                period = play.get('period')
                                clock = play.get('clock')
                                description = play.get('description', '')
                                print(f"NEW 3PT MADE [{game_id}] {period}-{clock}: {description}")
                                updated_desc = re.findall("^\w.\s\w+", description)
                                message_text = updated_desc[0] + " TREBALL FROM DEEP👌"
                                message(message_text)
                                new_plays_found = True
                                tracking['last_play_id'] = play.get('actionNumber', 0)  # Use actionNumber for live endpoint
                            elif play.get("actionType") == "ejection":
                                period = play.get('period')
                                clock = play.get('clock')
                                description = play.get('description', '')
                                print(f"EJECTION [{game_id}] {period}-{clock}: {description}")
                                message_text = f"EJECTION: {description}"
                                message(message_text)
                                new_plays_found = True
                                tracking['last_play_id'] = action_num
                    
                    if not new_plays_found:
                        print(f"[{game_id}] No new plays since last check.")

            elif is_game_over(game_id):
                print(f"Game {game_id} is over. Stopping monitoring for {game_id}.")
                games_to_remove.append(game_id)
            else:
                # Game might not be live yet, or status is unknown.
                # Keep it in monitored_games for now, it will be picked up by is_game_live check
                pass

        # Remove finished games from the monitored_games dictionary
        for game_id in games_to_remove:
            del monitored_games[game_id]
        
        # If no games are being monitored, break the loop
        if not monitored_games:
            print("All games are over. Stopping monitoring loop.")
            break

        # If no games are being monitored and no new games are expected to start soon,
        # we can break this inner loop and let the main loop handle the daily check.
        if not monitored_games and not any(game['game_id'] not in monitored_games for game in games_today):
            print("All active/upcoming games for today have been processed or are no longer live.")
            break

        time.sleep(5 if TEST_MODE else 5) # Shorter sleep for testing, normal sleep for production

def main():
    """Main function to run the NBA game monitor."""
    while True:
        print(f"\n--- Checking for today's NBA games on {datetime.now().strftime('%Y-%m-%d')} ---")
        todays_games = get_games_today()

        if todays_games:
            print("Games scheduled for today:")
            for game in todays_games:
                # Convert UTC start time to local timezone for display
                start_time_local = game['start_time_local'].astimezone(datetime.now().astimezone().tzinfo).strftime('%Y-%m-%d %H:%M:%S %Z%z')
                print(f"  Game ID: {game['game_id']}, Start Time (Local): {start_time_local}")
            
            # Start monitoring only when a game is expected to be live or is live
            monitor_games(todays_games)
            
            print("Finished monitoring all games for today.")
            if TEST_MODE: # In test mode, we break after one full cycle
                break
        else:
            print("No NBA games scheduled for today.")

        print("Waiting until the next day to check for games.")
        # Wait for approximately 24 hours before checking again
        # This sleep ensures the script doesn't hammer the API on days with no games
        time.sleep(24 * 3600)

if __name__ == "__main__":
    print("NBALiveSlack Monitor started.")
    main()