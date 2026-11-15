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
