# Pit Boss – project notes for Claude

Read this first. It explains what this repo is, how it runs, and the rules for changing it.

## What this is
Pit Boss is a Discord bot for the **Blue Chip** fantasy football league on MyFantasyLeague (MFL).
- League ID: `27743`, season `2026`, host `https://www48.myfantasyleague.com`
- League home: https://www48.myfantasyleague.com/2026/home/27743
- 32 teams, dynasty format with IDP (positions include DE, DT, LB, CB, S), salaries/contracts, taxi squad, IR, blind-bid waivers, future draft picks.
- Discord channel for automated posts: `#league-activity`

The people maintaining this are not professional developers. Keep code simple, standard-library-first, well commented, and give step-by-step, plain-English instructions for any setup change.

## The two parts

| File | What it does | Where it runs |
|---|---|---|
| `pitboss.py` | **Transaction feed.** Polls MFL transactions and posts new trades and adds/drops/waiver wins to `#league-activity` via a Discord **webhook**. Standard library only. | GitHub Actions, every 15 min (`.github/workflows/pitboss.yml`) |
| `state.json` | Feed's memory of already-posted transactions (hashes). Committed back to the repo by the workflow. **Don't delete or ignore it.** | written by the workflow |
| `pitboss_bot.py` | **Slash-command bot** (`discord.py`): `/standings`, `/roster`, `/player`, `/stats`. Uses the Pit Boss bot account (Developer Portal application). | Always-on machine (currently Mike's Windows PC) |
| `start_pitboss.bat` | Windows launcher: installs requirements, runs the bot, auto-restarts if it stops. | Windows PC |
| `requirements.txt` | Python packages for the command bot. | |
| `TODO.md` | Feature backlog. | |

## Secrets (never commit these)
- `DISCORD_WEBHOOK_URL` – GitHub Actions secret, used by `pitboss.py`.
- `MFL_API_KEY` – optional GitHub secret; only needed if the league becomes private.
- Discord **bot token** – in `token.txt` next to `pitboss_bot.py` (git-ignored) or the `DISCORD_BOT_TOKEN` env var on a server.

If a token or webhook URL ever gets committed or pasted somewhere public, reset it immediately (Discord Developer Portal → Bot → Reset Token; or delete/recreate the webhook).

## MFL API notes (verified against this league)
Base: `{HOST}/{YEAR}/export?TYPE=<type>&L=27743&JSON=1` – public for this league, no login needed.
- `transactions` (`DAYS=n`): types seen: `TRADE`, `FREE_AGENT`, `BBID_WAIVER`, `IR`, `LOCK_ALL_PLAYERS`, `UNLOCK_ALL_PLAYERS`, `BBID_AUTO_PROCESS_WAIVERS`.
  - TRADE: `franchise`, `franchise2`, `franchise1_gave_up`, `franchise2_gave_up` (comma-separated, trailing comma), `comments`, `by_commish`.
  - FREE_AGENT: `transaction` = `"added,|dropped,"`. BBID_WAIVER: `"added,|bid|dropped,"`.
  - IR: `activated`, `deactivated`.
  - Pick codes: `FP_<franchise>_<year>_<round>` (future), `DP_<round0>_<pick0>` (current year, 0-based), `BB_<amount>` (blind-bid dollars).
- `leagueStandings`: already sorted; fields `h2hwlt`, `pf`, `pa`, `pp` (potential points), `eff`, `strk`, `salary`.
- `playerScores` (`W=YTD` or week number, `POSITION`, `COUNT`, `PLAYERS`): sorted desc; `isAvailable` = "1" for free agents.
- `league` → `league.franchises.franchise[]` (id, name). `rosters` → `rosters.franchise[].player[]` (id, status ROSTER/TAXI_SQUAD/INJURED_RESERVE, salary, contractYear). `players` → names are `"Last, First"`.
- A single result may come back as an object instead of a list – always normalize (`as_list`).
- Other useful exports for the backlog: `tradeBait`, `injuries`, `nflSchedule`, `schedule`, `rules`, `liveScoring`.
- Send a descriptive User-Agent; don't poll faster than needed (cache 5–10 min).

## Conventions
- Times shown in US Central.
- Embed color gold `0xF1C40F` for command replies.
- Unknown player IDs display as `Player #<id>`, never crash.
- Test changes by running the "Pit Boss" workflow manually (Actions → Run workflow) or restarting `start_pitboss.bat`.
- When adding a command, register it with `@tree.command` in `pitboss_bot.py`; commands sync to each server on startup.
- Update `TODO.md` and this file when something ships or the setup changes.
