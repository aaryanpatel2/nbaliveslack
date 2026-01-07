# 🏀 NBA Live Game Notification Bot
A full-stack application designed to keep NBA fans updated with real-time, customizable notifications for live NBA games. As of right now, a Python backend processes game data from the [nba_api](https://github.com/swar/nba_api/tree/master) and dispatches personalized Slack notifications for custom game events.

### ✨ Features Implemented

- [x] Python backend script with play/team/player customization to deliver Slack notifications (able to run locally to achieve this process)
- [x] GitHub Actions workflow for automated post-game summaries

### 🎯 Future Goals
- [ ] Frontend UI (React) With a Database + Auth
- [ ] Backend API
- [ ] Slack Bot Real-Time Interaction With Commands
- [ ] Amazon SNS Integration

## 📊 Post-Game Summary Feature

The bot now includes automated post-game summaries via GitHub Actions! This feature sends Slack notifications after games with detailed shooting statistics.

### How It Works

The GitHub Actions workflow runs automatically at scheduled times and checks for completed games from the previous day. If a game is found, it sends a summary with:

- 🏆 Top performing shooter (configurable stat type)
- 📊 Complete list of all players who attempted shots
- 📈 Individual stats: Made/Attempts and Shooting Percentage

### Setup Instructions

1. **Add GitHub Secrets:**
   - Go to your repository → Settings → Secrets and variables → Actions
   - Add two secrets:
     - `SLACK_BOT_TOKEN`: Your Slack bot token
     - `SLACK_USER_ID`: Your Slack user ID or channel ID

2. **Customize Settings (Optional):**
   
   Edit [.github/workflows/post_game_summary.yml](.github/workflows/post_game_summary.yml):
   
   ```yaml
   # Change the default team (line 41)
   python post_game_summary.py --team "Lakers" --stat 3pt --days-back 1
   
   # Change the stat type:
   # Options: 3pt (3-pointers), fg (field goals), ft (free throws)
   python post_game_summary.py --team "OKC Thunder" --stat fg --days-back 1
   ```

3. **Schedule Times:**
   
   The workflow runs at:
   - 2 AM UTC (9 PM ET previous day)
   - 5 AM UTC (12 AM ET)
   - 8 AM UTC (3 AM ET)
   - 11 PM UTC (6 PM ET)
   
   To modify, edit the cron schedule in the workflow file.

### Manual Trigger

You can also trigger the summary manually:
1. Go to Actions tab in your repository
2. Select "NBA Post-Game Summary"
3. Click "Run workflow"
4. Customize team, stat type, and days to look back
5. Click "Run workflow"

### Supported Teams

All NBA teams are supported. Use common names like:
- `OKC Thunder` or `Thunder`
- `Lakers`
- `Warriors`
- `Celtics`
- `Heat`
- etc.

### Supported Stats

- `3pt` - Three-point shooting (default)
- `fg` - Field goal shooting
- `ft` - Free throw shooting

