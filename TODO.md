# Pit Boss – To-Do

Status key: ⬜ to do · 🔄 in progress · ✅ done

## Done
- ✅ Transaction feed (trades, adds/drops, blind-bid wins) → `#league-activity`
- ✅ Slash commands: `/standings`, `/roster`, `/player`, `/stats`
- ✅ `/topscorers` – top scorers for one NFL game window (was backlog #2)
- ✅ `/violationreport` – roster & lineup violations for every team (was backlog #4)

## Backlog
| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Run Pit Boss off one of Mike's servers instead of the PC | ⬜ | Need server details: OS, always-on, Python 3.10+. Bot already reads `DISCORD_BOT_TOKEN` env var. |
| 2 | Top scorers for a given NFL game window | ✅ | TNF, Sunday early/late, SNF, MNF – use `nflSchedule` kickoff times + weekly `playerScores`. |
| 3 | Trade Bait updates | ⬜ | Post when a team adds/changes its trade bait (`tradeBait` export). |
| 4 | Illegal Roster Report | ✅ | Over/under roster or position limits; starting injured/bye players. |
| 5 | Injury Report – IR activation | ⬜ | Healthy players still on IR; injured players not on IR (`injuries` + `rosters`). |
| 6 | Playoff Picture | ⬜ | Seeds, in/bubble/out, games back – standings + remaining schedule. |
| 7 | Potential Point Rankings | ⬜ | `leagueStandings` already has `pp` and `eff`. |
| 8 | Trade evaluator | ⬜ | Could use values from Mike's Dynasty Rankings & Trade Calculator. |
| 9 | Ability to spit back league rules | ⬜ | `/rules <topic>` from MFL league settings + league rules page/constitution. |
| 10 | Fix `/stats` position list | ⬜ | Uses QB/PK/PN/Def, but this league's positions are TMQB/TMPK/TMPN – those searches return nothing. |
| 11 | Auto-post Violation Report | ⬜ | Optional: post `/violationreport` results to Discord before Sunday kickoff. |
