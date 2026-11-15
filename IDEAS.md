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

## Considered and passed on

- **Linked Roles** (auto-give The Final Table role to MFL-verified owners). Passed Nov 15, 2026: it needs a public web page, the commissioner's MFL API key and an email-matching fallback, which isn't worth it for 32 owners the admins already know.
