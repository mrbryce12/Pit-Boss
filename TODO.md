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

- ✅ AI chat: @Pit Boss answers questions (live MFL data, rule book, trade opinions, NFL chat), persona file, learns via trainer-approved memories (was backlog #9 rules + #8 trade opinions, partial)

## Backlog
| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Run Pit Boss off one of Mike's servers instead of the PC | ⬜ | Need server details: OS, always-on, Python 3.10+. Bot already reads `DISCORD_BOT_TOKEN` env var. |
| 2 | Top scorers for a given NFL game window | ✅ | TNF, Sunday early/late, SNF, MNF – use `nflSchedule` kickoff times + weekly `playerScores`. |
| 3 | Trade Bait updates | ⬜ | Post when a team adds/changes its trade bait (`tradeBait` export). |
| 4 | Illegal Roster Report | ✅ | Over/under roster or position limits; starting injured/bye players. |
| 5 | Injury Report – IR activation | ⬜ | Healthy players still on IR; injured players not on IR (`injuries` + `rosters`). |
| 6 | Playoff Picture | ✅ | 12 teams per rule book: 4 division winners (seeds 1-4, bye), 8 wild cards; Week 14 matchups; first 4 out with games back. Possible add-on: remaining schedule / magic numbers. |
| 7 | Potential Point Rankings | ✅ | All 32 by PP with eff, record, playoff seed; 8 lowest-PP non-playoff teams get lottery balls 8→1 (rule book §14b). |
| 8 | Trade evaluator | ⬜ | Could use values from Mike's Dynasty Rankings & Trade Calculator. |
| 9 | Ability to spit back league rules | ⬜ | `/rules <topic>` from MFL league settings + league rules page/constitution. |
| 10 | Fix `/stats` position list | ⬜ | Uses QB/PK/PN/Def, but this league's positions are TMQB/TMPK/TMPN – those searches return nothing. |
| 11 | Auto-post Roster Alerts | ⬜ | Optional: post `/rosteralerts` results to Discord before Sunday kickoff. |
| 12 | AI: plug Mike's dynasty trade values into trade opinions | ⬜ | Export values to a CSV the AI can read. |
| 13 | AI: link Discord users to their MFL teams | ⬜ | Trainers can /teach "Mike runs X" today; could become a /iam command. |
