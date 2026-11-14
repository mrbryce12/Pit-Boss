# 🎰 Pit Boss

Discord bot for the **Blue Chip** MFL league.

- **Transaction feed** – posts trades and roster moves to `#league-activity` every 15 minutes (runs free on GitHub Actions).
- **Slash commands** – `/standings`, `/roster`, `/player`, `/stats` (runs on an always-on computer).

Working with Claude on this? Have it read [`CLAUDE.md`](CLAUDE.md) first. Feature ideas live in [`TODO.md`](TODO.md).

## Transaction feed setup
1. Discord: channel settings → Integrations → Webhooks → New Webhook → copy URL.
2. GitHub repo → Settings → Secrets and variables → Actions → New repository secret: `DISCORD_WEBHOOK_URL`.
3. Actions tab → Pit Boss → Run workflow. You should see "The Pit Boss is on the floor" in Discord.

## Command bot setup (Windows)
1. Install Python from python.org (check "Add python.exe to PATH").
2. Download this repo (green **Code** button → Download ZIP) and unzip it.
3. Create `token.txt` next to `pitboss_bot.py` and paste the bot token in (Developer Portal → Bot → Reset Token).
4. Double-click `start_pitboss.bat` and leave the window open.

On a Linux/Mac server: `pip install -r requirements.txt`, set `DISCORD_BOT_TOKEN`, run `python pitboss_bot.py`.

## AI chat (optional)
1. Create an API key at console.anthropic.com (add a small prepaid balance).
2. Put it in `anthropic_key.txt` next to `pitboss_bot.py` and restart `start_pitboss.bat`.
3. In Discord: `@Pit Boss who leads the league?` – or reply to any Pit Boss message.
4. Change his personality in `personality/persona.md`. Trainers (Manage Server or the "Pit Boss Trainer" role) use `/teach`, `/memories`, `/approve`, `/forget`, `/aiusage`.

## Never commit secrets
`token.txt` and `anthropic_key.txt` are git-ignored. Webhook URL and API keys go in GitHub Secrets only.
