# Pit Boss – ideas to revisit

Ideas we like but haven't committed to yet. They are **not** on the to-do list.
When one is approved, move it to `TODO.md`.

---

## Sportsbook (play money)

*Parked Nov 15, 2026.*

Owners bet fake chips on Blue Chip matchups, and Pit Boss acts as the house.

**Ground rules**
- Play money only: no cash and no prizes with real value, so it stays a game.
- Owners can bet on their own game, but only on **themselves to win**, so nobody profits from losing.
- Standard −110 juice, so picking 50/50 slowly loses chips and it stays a skill game.
- An owner who runs out of chips can rebuy a small amount, with a leaderboard penalty.
- The season's top bankroll gets a "High Roller" role for the next year, plus a Hall of Fame mention.

**How it works**
- **Lines are automatic.** MFL's `weeklyResults` already has a `spread` for each matchup (e.g. `-18.6`). Moneylines and over/unders come from that plus `projectedScores`.
- **Bets lock** at Thursday kickoff (first game in `nflSchedule` for the week).
- **Settlement** is automatic on Tuesday, once `weeklyResults` is final. Pit Boss posts the results, the week's biggest winner and the "bad beat of the week."

**Bet types**
- Version 1: spread, moneyline, team-total over/under.
- Version 2: props (high score, low score, closest game, top IDP), parlays, futures (champion, division winners, #1 lottery pick; odds from `playoff_picture()` and the power rankings).

**Commands:** `/lines`, `/bet`, `/mybets`, `/bankroll`, `/leaderboard`, `/futures`

**Build notes**
- Store bets and bankrolls in `data/sportsbook.json` on the bot machine. It's git-ignored like the other `data/` files, so back it up and move it if the bot moves.
- Use a scheduled loop like the Saturday lineup reminder (`tasks.loop`) to lock bets and settle the week.
- Effort: Version 1 is about a couple of evenings, since matchups, spreads and scores already come from MFL.

**Open decisions for the committee**
1. **Chips:** a fresh weekly allowance (e.g. 1,000 a week, which levels the field), or one season bankroll (e.g. 10,000, which rewards money management)?
2. **Channel:** a new `#sportsbook` channel, or `#pit-boss-reports`?
3. **Start date:** now (last regular-season weeks plus the playoffs), or a full launch next season?

---

## Linked Roles (MFL-verified owner role)

*Parked Nov 15, 2026. Low priority: admins already know all 32 owners, so the main gain is not having to hand out roles and having verified team ownership instead of self-declared `/iam`.*

Discord gives an owner a role automatically once Pit Boss confirms they own an MFL team.

**How it works for an owner**
1. In Discord: server menu → **Linked Roles** → click **The Final Table**.
2. Discord opens a small Pit Boss web page, where the owner approves "Pit Boss can see your account."
3. Pit Boss checks MFL. If the person owns a team, it tells Discord "verified owner of [team]."
4. Discord gives the role. No admin step.

**Verifying MFL ownership (never ask for MFL passwords)**
- First choice, email match: Discord OAuth (`identify email` scopes) gives the owner's verified email, and the `league` export read with the commissioner's MFL API key includes each franchise owner's email. If they match, the owner is verified. *Check first that the API key really returns owner emails for this league.*
- Fallback when emails differ: Pit Boss shows a short code, the owner puts it in their MFL team profile or league chat, and Pit Boss checks for it. A committee member can also approve someone by hand.

**What to build**
1. **Role connection metadata.** Register once via the Discord API: `verified_owner` (yes/no), `seasons_in_league` (number), `championships` (number).
2. **Verification web endpoint.** Discord requires a public HTTPS "Linked Roles Verification URL" and an OAuth2 redirect. The bot PC isn't reachable from the internet, so use a free tunnel (e.g. Cloudflare Tunnel) or a small free web host.
3. **The ownership check:** email match first, then the code fallback. On success, `PUT /users/@me/applications/{app_id}/role-connection` with the metadata.
4. **Discord settings (an admin, no code):**
   - Developer Portal → General Information: set the Linked Roles Verification URL.
   - OAuth2: add the redirect, and keep the client secret off GitHub.
   - Server Settings → Roles → **The Final Table** → Links: add the requirement "Pit Boss: verified owner = true."

**Bonus roles from the same data:** Champion (championships ≥ 1), OG (seasons ≥ 10), and division roles, all updating automatically. It would also replace `/iam` with verified ownership.

**Needs:** the commissioner's MFL API key (kept on the bot machine like `token.txt`), a hosting choice (tunnel vs. free host), and Developer Portal access.

**Effort:** a few evenings. Build as `pitboss_linkedroles.py`, hooked into the bot the way `pitboss_ai.py` is.

---

## Shared building blocks for the ideas below

Several ideas reuse the same pieces. Build each once:
- **Owner directory:** `data/owners.json` (Discord user → MFL franchise), filled by `/iam` and `/setowner`. Any feature that gives an owner a role or a personal stat needs it, so every owner should run `/iam`.
- **Scheduled jobs:** a `tasks.loop` that remembers its last run in `data/`, like the Saturday lineup reminder (`lineup_reminder_loop`).
- **Play-money wallet:** if the sportsbook and prediction markets both get built, they should share one chip balance per owner (`data/wallet.json`), not two.
- **Bot permissions:** Manage Roles (trophy roles) and Manage Channels (tickers), with the Pit Boss role placed above any role it hands out.

---

## Activities night (poker, games, watch-alongs)

*Parked Nov 15, 2026.*

**What:** a regular league night using Discord's built-in Activities, the games and apps that run inside a voice call: Poker Night, card games, chess, mini-golf, and Watch Together for YouTube. Poker fits the casino theme.

**What Discord already provides (no code)**
- In any voice channel: click the rocket icon (Activities) → pick a game. Everyone in the call plays together.
- Check the current Activities list and requirements in Discord before announcing. Some Activities have had age or server-boost requirements in the past.

**What Pit Boss adds**
1. **`/gamenight` (admins).** Creates a Discord Scheduled Event (discord.py `guild.create_scheduled_event`) in League Voice Chat, with the date, time and game. Owners click "Interested" and Discord reminds them.
2. **Announcement:** posts in #league-chat when the event is created, and again 30 minutes before.
3. **Poker standings:** `/pokerresult @winner [@2nd @3rd]` (admins) records each night's finish in `data/poker.json`, and `/pokerstandings` shows the season table. The season winner could get a trophy role (see Trophy roles).

**Suggested rhythm:** monthly in the off-season, or during the bye-week lull. A "Pit Boss Poker Night" before the rookie draft is a good kickoff.

**Effort:** a couple of hours. It's mostly the Scheduled Event command and a small standings file.

---

## Trophy roles (champions, records, server tag)

*Parked Nov 15, 2026.*

**What:** roles that work as trophies, visible next to an owner's name everywhere in the server, given automatically from league history.

**Roles**
- 🏆 **Reigning Champion:** last season's title winner, in gold, shown separately in the member list.
- **Champion (any year):** everyone who has won a Blue Chip title. Names could carry the years, e.g. a role per title like "Champion 2024."
- **Runner-up** for last season.
- **Record holders:** Highest Single-Week Score (all time), Highest Season PF, Longest Win Streak. These move when a record falls.
- **Season awards:** if member-voted awards happen (MVP GM, Trade of the Year), the winner gets a role for the next season.
- **Poker / sportsbook champion,** if those get built.

**Data sources (all exist already in `pitboss_ai.py`)**
- `league_champions()`: the official champions table on the MFL home page, every season since 2014, with franchise ids.
- `weekly_records()` / `history_standings`: high scores, season PF and streaks.
- The owner directory maps each franchise to a Discord member.

**How it works**
1. **One-time setup (admin):** create the roles with colors, or let Pit Boss create them, and put the Pit Boss role above them.
2. **`/trophysync` (admins):** recomputes who should hold each role and adds or removes it. It posts a summary like "🏆 Reigning Champion: Penn State Nittany Lions (@owner)."
3. **Automatic:** a scheduled job runs `/trophysync` after the championship week is final (Week 17), and weekly for record roles.
4. **A franchise that changed hands:** trophies follow the franchise's current owner, or the person who won it if they're still in the league. That's a committee decision.
5. **`/trophies [team]`:** lists a team's titles and records.

**Extras that cost Discord boosts (check current boost levels in Server Settings)**
- **Role icons:** small images next to names, such as a trophy emoji. These need a higher server boost level.
- **Server tag:** a short league tag members can show next to their name across Discord. This also needs boosts.

**Effort:** an evening. The history data is already there; the new parts are role syncing and permissions.

---

## Prediction markets (play money)

*Parked Nov 15, 2026.*

**What:** owners buy and sell play-money "shares" in season questions. The price moves as people trade, so it shows what the league collectively thinks, e.g. "Will Hot Mess win a game? YES 18¢."

**Example markets**
- Who wins the title? (one market per contender)
- Will any team finish 0-17? Will the 12 seed have a losing record?
- Will a trade happen before the deadline involving a 1st-round pick?
- Who gets the 1.01 lottery pick?
- Rule-change votes: "Will the proposal pass?"

**How trading works**
- Each market has YES and NO shares that pay 100 chips if right and 0 if wrong.
- Prices come from a standard automated market maker (LMSR), so there's always someone to trade with and prices move smoothly. There's no order book to manage.
- Owners trade with chips from the shared play-money wallet.

**Commands**
- `/markets`: open markets with current prices.
- `/buy market:<name> side:<yes|no> chips:<n>` and `/sell`.
- `/portfolio`: your positions and paper profit.
- Trainers or commissioners: `/market create`, `/market close`, `/market resolve <yes|no>`.

**Auto-resolution where possible:** markets tied to MFL data (champion, records, lottery winner) resolve on their own from MFL exports. Anything else is resolved by a trainer, with the result posted publicly.

**Fairness rules**
- No buying NO on your own team's success, and no YES on your own failure, so nobody gains from tanking.
- Markets lock before the outcome can be known, e.g. at kickoff.
- All trades are public in a #markets channel or thread, for transparency.

**Storage:** `data/markets.json` (markets, trades, positions).

**Effort:** 2–3 evenings. The market math is short, but resolution, locking and the commands take the time. It's best built after the sportsbook, so they share the wallet.

---

## AI-voiced weekly recap ("The Pit Boss Report")

*Parked Nov 15, 2026.*

**What:** every Monday morning, a 2–3 minute audio recap of the week in Pit Boss's voice, posted as a playable audio file.

**Pipeline**
1. **Gather the week's facts in code** (no AI arithmetic): the `/recap` data (results, high/low, blowout, closest game, bench points, players of the week), power-ranking moves, the playoff picture changes, and notable trades.
2. **Write the script with Claude**, using `personality/persona.md` for the voice. Target about 350–450 words (≈2.5 minutes) and a fixed structure: open, top games, awards, playoff race, closing line. Script length is capped, and the script is posted as text too.
3. **Turn the script into speech (TTS).** Options:
   - **Piper** (free, open-source, runs locally on the bot PC; decent voices, no account).
   - **A paid cloud TTS** (e.g. ElevenLabs, OpenAI, Google Cloud TTS). These have the most natural voices and charge per character, typically cents per episode. Compare current pricing first.
   - Claude doesn't produce audio, so a separate TTS service is needed either way.
4. **Post it:** upload the MP3 to #pit-boss-reports or #league-chat with a short text summary. A 3-minute MP3 is ~2–3 MB, well under Discord's upload limit.
5. **Archive:** keep episodes in `data/podcast/` so you can make a season compilation.

**Version 2:** Pit Boss joins a Stage channel and plays the episode live as a "broadcast." That needs `PyNaCl` and `ffmpeg` on the bot PC. You could also do special episodes for the trade deadline, the playoffs and the rookie draft.

**Settings:** day and time (Monday 9 AM CT), channel, voice, maximum length, and an on/off switch.

**Cost:** one Claude call per week (small, counted in `/aiusage`) plus TTS (free with Piper; cents with a cloud voice).

**Effort:** 1–2 evenings for version 1.

---

## Live channel-name tickers

*Parked Nov 15, 2026.*

**What:** a few channels at the top of the sidebar whose names update themselves, so the sidebar works like a scoreboard. Members see them without opening anything.

**Examples**
- 🏈 Week 10 · 4 games live
- 📅 Trade deadline in 3 days
- 🏆 Playoffs start in 4 weeks
- 🔥 Top score: The Mandalorian 295.8
- 💰 Rookie draft in 21 days (off-season)

**How it works**
1. **Admin setup:** create a "📊 Scoreboard" category with 2–4 voice channels that nobody can join (deny Connect for @everyone). Voice channels show their full name nicely and can't fill up with chat.
2. **Pit Boss renames them on a schedule:** `channel.edit(name=...)` with live data from `nflSchedule` (games live now), `liveScoring` and the standings.
3. **Dates that MFL doesn't publish:** trade deadline, rookie draft, dues deadline, set in a small `tickers` settings block (or `/ticker set` for admins).

**Discord's limits (important)**
- Discord only allows about **2 renames per channel every 10 minutes**. Update every 10–15 minutes, and only when the text actually changes.
- Pit Boss needs **Manage Channels** on that category.
- Keep names short; long names get cut off in the sidebar.

**Settings:** which tickers are on, update interval, and the event dates above.

**Effort:** an evening.

---

## Year-end "Blue Chip Wrapped"

*Parked Nov 15, 2026.*

**What:** a Spotify-style recap for every owner after the season, plus one for the whole league. It's fun, shareable, and gets everyone talking during the off-season.

**Each owner's Wrapped**
- Final record, finish, PF rank, and luck (actual wins vs. all-play expected wins).
- Best and worst week (scores and opponents).
- **MVP:** the player with the most points in their starting lineup (from `weeklyResults` player lists).
- **Best pickup:** a free agent or waiver add who scored the most for them after joining.
- **Best and worst trade:** points gained or lost from players received vs. sent, after the trade date.
- **Bench points left behind** for the season, and the single worst lineup decision.
- Trades made, waiver bids, IR and taxi moves.
- Pit Boss stats: AI questions asked, most-used command (from `data/usage.json`).
- Optional chat stats: messages posted in league channels (counts only, never content). Make this opt-in.

**League Wrapped:** champion, best regular season, most trades, biggest blowout, closest game, top pickup across the league, most bench points left, luckiest and unluckiest team.

**Delivery**
1. **Cards as images:** Pit Boss draws a few slides per owner with Pillow (Python imaging), in Blue Chip colors.
2. **Posting:** a #wrapped thread with one post per team, or a private DM to each owner (opt-in) plus the league Wrapped in public.
3. **Timing:** a scheduled job the week after the championship (Week 17 final), or `/wrapped` (admins) to run it.

**Data:** everything comes from MFL exports Pit Boss already reads: `weeklyResults` (per-player starter points), `transactions` (adds, trades, dates), `playerScores` by week, and `leagueStandings`. Discord stats come from `data/usage.json`, plus the opt-in message counts.

**Effort:** 3–4 evenings. The stats are straightforward; the image cards take the most polish. A text-only version could ship in an evening.
