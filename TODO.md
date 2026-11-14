# Pit Boss – To-Do

Status key: ⬜ to do · 🔄 in progress · ✅ done

## Done
- ✅ Transaction feed (trades, adds/drops, blind-bid wins) → `#league-activity`
- ✅ Slash commands: `/standings`, `/roster`, `/player`, `/stats`
- ✅ `/topscorers` – top 5 scorers at each position (RB, WR, TE, DE, DT, LB, CB, S) for one NFL game window (was backlog #2)
- ✅ `/rosteralerts` – roster & lineup problems for all teams (was backlog #4)
- ✅ `/rosterviolations` – illegal rosters only, all teams
- ✅ `/playoffs` – playoff picture if the season ended today (was backlog #6)
- ✅ `/potentialpoints` – PP rankings for all teams + draft lottery balls (was backlog #7)
- ✅ `/tradebait` (one team, with salaries) and `/tradebaitall` (every team, newest first) (was backlog #3)
- ✅ `/ircheck` – players on IR who are no longer IR-eligible (rule book §4), with roster/cap impact of activating (was backlog #5)
- ✅ Standard reports: `/recap` (results + awards), `/matchups` (records, PF/PP, seeds, division/playoff-race flags, live scores), `/powerrankings` (all-play, luck, last 3 weeks), `/capspace`, `/capnextyear` (rollover), `/owneractivity` (admins), `/trades` (recent + per-team counts)
- ✅ Saturday lineup reminder: posts Roster Alerts to `#league-activity` at 7 PM CT; `/lineupreminder` (admins) posts it now (was backlog #11)

- ✅ AI chat: @Pit Boss answers questions (live MFL data, rule book, trade opinions, NFL chat), persona file, learns via trainer-approved memories (was backlog #9 rules + #8 trade opinions, partial)
- ✅ AI calculators: cap/next-season rollover, tags, holdouts, salary tiers, scoring stats, power rankings/luck, records, head-to-head, positional strength, trade math, league cap table, what-if playoffs
- ✅ AI league info: start/sit (RotoWire + Ourlads), message board, public chat, owner activity, history 2014+, future picks, projected draft order
- ✅ AI ops: one AI channel, 5 questions/day per person (trainers exempt), owner directory (`/iam`), channel memory for follow-ups

## Backlog
| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Run Pit Boss off one of Mike's servers instead of the PC | ⬜ | Need server details: OS, always-on, Python 3.10+. Bot already reads `DISCORD_BOT_TOKEN` env var. |
| 2 | Top scorers for a given NFL game window | ✅ | TNF, Sunday early/late, SNF, MNF – use `nflSchedule` kickoff times + weekly `playerScores`. |
| 3 | Trade Bait updates | ✅ | `/tradebait` + `/tradebaitall`. Auto-posting when bait changes is #14. |
| 4 | Illegal Roster Report | ✅ | Over/under roster or position limits; starting injured/bye players. |
| 5 | Injury Report – IR activation | ✅ | `/ircheck`: IR players without an IR/IR-R/IR-PUP/IR-NFI/Suspended designation, or team positions, must be activated or cut (rule book §4b–c). Could also be added to `/rosterviolations` or the auto-check (#14). |
| 6 | Playoff Picture | ✅ | 12 teams per rule book: 4 division winners (seeds 1-4, bye), 8 wild cards; Week 14 matchups; first 4 out with games back. AI what-ifs (season ended week N, team wins out) added. Possible add-on: magic numbers. |
| 7 | Potential Point Rankings | ✅ | All 32 by PP with eff, record, playoff seed; 8 lowest-PP non-playoff teams get lottery balls 8→1 (rule book §14b). |
| 8 | Trade evaluator | 🔄 | AI trade opinions + `trade_compare` (salary now/next year/total owed, points, injuries) done. Remaining: plug in dynasty trade values (#12). |
| 9 | Ability to spit back league rules | ✅ | Done via AI chat: reads the Blue Chip rule book (Godfather site, daily) + MFL settings, cites sections. A `/rules` slash command is optional. |
| 10 | Fix `/stats` position list | ⬜ | Uses QB/PK/PN/Def, but this league's positions are TMQB/TMPK/TMPN – those searches return nothing. |
| 11 | Auto-post Roster Alerts | ✅ | Saturday 7 PM CT to `#league-activity` (settings `LINEUP_REMINDER_*` in `pitboss_bot.py`); `/lineupreminder` to post now. |
| 12 | AI: plug Mike's dynasty trade values into trade opinions | ⬜ | Export values to a CSV the AI can read. |
| 13 | AI: link Discord users to their MFL teams | ✅ | `/iam`, `/setowner` (trainers), `/owners`; stored in `data/owners.json`. |
| 14 | Auto-check MFL for updates: transactions, trades, trade bait | ✅ | Poll MFL every ~15 min and post anything new to Discord. Transactions + trades already post via `pitboss.py` (GitHub Actions, every 15 min) – extend that (or move polling into the bot) to also post a team's trade bait card (`tradebait_embed()`) when its `tradeBait` timestamp changes. Remember last-seen timestamps (like `state.json`). |
| 15 | Generate the initial announcement | ⬜ | Launch post introducing Pit Boss: what he does, how to ask (@Pit Boss, slash commands), /iam, daily limits. |
| 16 | Generate the "about the league" description | ⬜ | Blue Chip overview for Discord (format, cap, contracts, playoffs, rule book links). |
| 17 | Scheduled reports to #pit-boss-reports | ⬜ | Pit Boss auto-posts on a schedule (e.g., weekly power rankings, playoff picture, cap table, injury/IR report, Sunday roster alerts). |
| 18 | Rules mastery: make sure Pit Boss fully knows both rule books and how to apply/interpret them | ⬜ | Build a rules test set (tricky questions with known answers: cap, contracts, tags, holdouts, IR/taxi, vetoes, tiebreakers, draft, conflicts between books), run it, fix gaps with commissioner notes / memories / code, re-test. |
| 19 | Calculation mastery: verify every cap/contract calculation | ⬜ | Hand-check each calculator against real league cases and the official sheets: cap number & room (this season / next season rollover), 20% escalation, cap +5%, IR/taxi %, dead money from cuts (rule 8i), franchise / exclusive / transition tag prices, holdout Stage 1/2 salaries, extensions, rookie salaries, trade total-owed math. Compare with the commissioner's Holdout & Tag sheet and cap tracker; fix differences; keep the test cases in the repo. |
