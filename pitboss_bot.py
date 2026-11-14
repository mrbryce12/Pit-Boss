"""
Pit Boss - Blue Chip league Discord bot (slash commands).

Commands:
  /standings                 - league standings
  /roster team:<team>        - a team's roster
  /player name:<player>      - who owns a player + season points
  /stats position:<pos> [week] [available_only]
                             - top fantasy scorers at a position

Setup: put the bot token in token.txt (same folder), then run start_pitboss.bat.
On a server, set the DISCORD_BOT_TOKEN environment variable instead.
"""

import os
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp
import discord
from discord import app_commands

# ---- League settings -------------------------------------------------------
LEAGUE_ID = "27743"
YEAR = "2026"
HOST = "https://www48.myfantasyleague.com"
API_HOST = "https://api.myfantasyleague.com"  # some exports (e.g. nflSchedule) only work here
CENTRAL = ZoneInfo("America/Chicago")  # league times are shown in US Central
LEAGUE_URL = f"{HOST}/{YEAR}/home/{LEAGUE_ID}"
USER_AGENT = "PitBossDiscordBot/1.0 (Blue Chip league)"
API_KEY = ""  # only needed if the league is ever made private

HERE = Path(__file__).parent
# Token comes from the DISCORD_BOT_TOKEN environment variable (servers)
# or from token.txt next to this file (Windows PC). Never commit either.
TOKEN = os.environ.get("DISCORD_BOT_TOKEN") or (HERE / "token.txt").read_text().strip()

POS_ORDER = ["QB", "RB", "WR", "TE", "PK", "PN", "Def",
             "DE", "DT", "LB", "CB", "S"]
GOLD = 0xF1C40F


# ---- MFL data with simple caching ------------------------------------------
class MFL:
    def __init__(self):
        self.session = None
        self.cache = {}  # key -> (time, data)

    async def get(self, type_, max_age=300, host=HOST, **params):
        key = (host, type_, tuple(sorted(params.items())))
        hit = self.cache.get(key)
        if hit and time.time() - hit[0] < max_age:
            return hit[1]
        if self.session is None:
            self.session = aiohttp.ClientSession(headers={"User-Agent": USER_AGENT})
        q = {"TYPE": type_, "JSON": "1", **params}
        if host == HOST:
            q["L"] = LEAGUE_ID  # NFL-wide exports on API_HOST must NOT send a league id
        if API_KEY:
            q["APIKEY"] = API_KEY
        async with self.session.get(f"{host}/{YEAR}/export", params=q,
                                    timeout=aiohttp.ClientTimeout(total=30)) as r:
            data = await r.json(content_type=None)
        self.cache[key] = (time.time(), data)
        return data

    async def teams(self):
        d = await self.get("league", max_age=86400)
        # Some owners style their team name with HTML (e.g. <font color=...>);
        # strip the tags so Discord shows plain text.
        return {f["id"]: re.sub(r"<[^>]+>", "", f.get("name", f["id"])).strip() or f["id"]
                for f in as_list(d["league"]["franchises"]["franchise"])}

    async def players(self):
        d = await self.get("players", max_age=86400)
        out = {}
        for p in as_list(d["players"]["player"]):
            out[p["id"]] = {
                "name": nice_name(p.get("name", p["id"])),
                "pos": p.get("position", ""),
                "team": p.get("team", ""),
            }
        return out

    async def rosters(self):
        d = await self.get("rosters", max_age=300)
        return as_list(d["rosters"]["franchise"])

    async def owners(self):
        """player id -> (franchise id, roster entry)"""
        out = {}
        for fr in await self.rosters():
            for p in as_list(fr.get("player")):
                out[p["id"]] = (fr["id"], p)
        return out


def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def nice_name(raw):
    if ", " in raw:
        last, first = raw.split(", ", 1)
        return f"{first} {last}"
    return raw


def tag(p):
    return " ".join(x for x in [p["pos"], p["team"]] if x)


mfl = MFL()
intents = discord.Intents.default()
# Lets Pit Boss read the text of messages where he is tagged (incl. his role) or replied to.
# Requires: Developer Portal > Pit Boss > Bot > "Message Content Intent" switched ON.
intents.message_content = True
# Lets Pit Boss see new members join so he can give them the starter role.
# Requires: Developer Portal > Pit Boss > Bot > "Server Members Intent" switched ON.
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


# ---- Autocomplete helpers --------------------------------------------------
async def team_autocomplete(_inter, current: str):
    teams = await mfl.teams()
    cur = current.lower()
    hits = [(fid, n) for fid, n in teams.items() if cur in n.lower()]
    return [app_commands.Choice(name=n[:100], value=fid) for fid, n in hits[:25]]


async def player_autocomplete(_inter, current: str):
    if len(current) < 2:
        return []
    players = await mfl.players()
    words = current.lower().split()
    hits = [(pid, p) for pid, p in players.items()
            if all(w in p["name"].lower() for w in words)]
    hits.sort(key=lambda x: x[1]["name"])
    return [app_commands.Choice(name=f"{p['name']} ({tag(p)})"[:100], value=pid)
            for pid, p in hits[:25]]


async def position_autocomplete(_inter, current: str):
    return [app_commands.Choice(name=p, value=p)
            for p in POS_ORDER if current.lower() in p.lower()][:25]


def find_team(value, teams):
    if value in teams:
        return value
    v = value.lower()
    for fid, n in teams.items():
        if v in n.lower():
            return fid
    return None


def find_player(value, players):
    if value in players:
        return value
    words = value.lower().split()
    for pid, p in players.items():
        if all(w in p["name"].lower() for w in words):
            return pid
    return None


# ---- Commands --------------------------------------------------------------
@tree.command(name="standings", description="Blue Chip league standings")
async def standings(inter: discord.Interaction):
    await inter.response.defer()
    teams = await mfl.teams()
    d = await mfl.get("leagueStandings", max_age=600)
    rows = as_list(d["leagueStandings"]["franchise"])
    lines = [f"{'#':>2}  {'Team':<22} {'W-L-T':<7} {'PF':>8}"]
    for i, r in enumerate(rows, 1):
        name = teams.get(r["id"], r["id"])[:22]
        wlt = r.get("h2hwlt") or f"{r.get('h2hw','0')}-{r.get('h2hl','0')}-{r.get('h2ht','0')}"
        lines.append(f"{i:>2}  {name:<22} {wlt:<7} {float(r.get('pf', 0)):>8.1f}")
    # Discord limit: split into chunks under 4000 chars
    text = "\n".join(lines)
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) > 3900:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    chunks.append(cur)
    embeds = [discord.Embed(description=f"```\n{c}```", color=GOLD) for c in chunks]
    embeds[0].title = "🏆 Blue Chip Standings"
    embeds[0].url = LEAGUE_URL
    await inter.followup.send(embeds=embeds[:10])


@tree.command(name="roster", description="Show a team's roster")
@app_commands.describe(team="Start typing a team name")
@app_commands.autocomplete(team=team_autocomplete)
async def roster(inter: discord.Interaction, team: str):
    await inter.response.defer()
    teams = await mfl.teams()
    fid = find_team(team, teams)
    if not fid:
        await inter.followup.send(f"Couldn't find a team matching **{team}**.")
        return
    players = await mfl.players()
    fr = next((f for f in await mfl.rosters() if f["id"] == fid), None)
    entries = as_list(fr.get("player")) if fr else []

    groups = {"ROSTER": {}, "TAXI_SQUAD": {}, "INJURED_RESERVE": {}}
    for e in entries:
        p = players.get(e["id"], {"name": f"Player #{e['id']}", "pos": "?", "team": ""})
        line = f"{p['name']} ({p['team'] or 'FA'})"
        extra = []
        if e.get("salary"):
            extra.append(f"${e['salary']}")
        if e.get("contractInfo"):  # contractInfo = years REMAINING (contractYear = original length)
            extra.append(f"{e['contractInfo']} yr left")
        if extra:
            line += " — " + ", ".join(extra)
        groups.setdefault(e.get("status", "ROSTER"), {}).setdefault(p["pos"], []).append(line)

    embed = discord.Embed(title=f"📋 {teams[fid]}", color=GOLD,
                          url=f"{HOST}/{YEAR}/options?L={LEAGUE_ID}&O=07&F={fid}")
    for pos in POS_ORDER + sorted({p for g in groups.values() for p in g} - set(POS_ORDER)):
        if pos in groups["ROSTER"]:
            embed.add_field(name=pos, value="\n".join(groups["ROSTER"][pos])[:1024], inline=False)
    for status, label in (("TAXI_SQUAD", "🚕 Taxi Squad"), ("INJURED_RESERVE", "🚑 Injured Reserve")):
        lines = [l for pos_lines in groups.get(status, {}).values() for l in pos_lines]
        if lines:
            embed.add_field(name=label, value="\n".join(lines)[:1024], inline=False)
    embed.set_footer(text=f"{len(entries)} players")
    await inter.followup.send(embed=embed)


@tree.command(name="player", description="Who owns a player, plus season points")
@app_commands.describe(name="Start typing a player name")
@app_commands.autocomplete(name=player_autocomplete)
async def player(inter: discord.Interaction, name: str):
    await inter.response.defer()
    players = await mfl.players()
    pid = find_player(name, players)
    if not pid:
        await inter.followup.send(f"Couldn't find a player matching **{name}**.")
        return
    p = players[pid]
    teams = await mfl.teams()
    owners = await mfl.owners()
    sc = await mfl.get("playerScores", max_age=600, W="YTD", PLAYERS=pid)
    score = next((s.get("score") for s in as_list(sc.get("playerScores", {}).get("playerScore"))
                  if s.get("id") == pid), None)

    embed = discord.Embed(title=f"🏈 {p['name']}", description=tag(p) or None, color=GOLD,
                          url=f"{HOST}/{YEAR}/player?L={LEAGUE_ID}&P={pid}")
    if pid in owners:
        fid, entry = owners[pid]
        status = {"TAXI_SQUAD": " (Taxi)", "INJURED_RESERVE": " (IR)"}.get(entry.get("status"), "")
        embed.add_field(name="Owner", value=teams.get(fid, fid) + status, inline=True)
        if entry.get("salary"):
            embed.add_field(name="Salary", value=f"${entry['salary']}", inline=True)
        if entry.get("contractInfo"):  # years REMAINING
            orig = f" (of {entry['contractYear']})" if entry.get("contractYear") else ""
            embed.add_field(name="Years left", value=f"{entry['contractInfo']}{orig}", inline=True)
    else:
        embed.add_field(name="Owner", value="🟢 Free Agent", inline=True)
    embed.add_field(name=f"{YEAR} Points", value=score or "0", inline=True)
    await inter.followup.send(embed=embed)


@tree.command(name="stats", description="Top fantasy scorers at a position")
@app_commands.describe(position="QB, RB, WR, TE, DE, DT, LB, CB, S...",
                       week="Week number (leave blank for full season)",
                       available_only="Only show free agents")
@app_commands.autocomplete(position=position_autocomplete)
async def stats(inter: discord.Interaction, position: str,
                week: app_commands.Range[int, 1, 18] = None,
                available_only: bool = False):
    await inter.response.defer()
    pos = next((p for p in POS_ORDER if p.lower() == position.lower()), position.upper())
    w = str(week) if week else "YTD"
    d = await mfl.get("playerScores", max_age=600, W=w, POSITION=pos,
                      COUNT="300" if available_only else "15")
    rows = as_list(d.get("playerScores", {}).get("playerScore"))
    if available_only:
        rows = [r for r in rows if r.get("isAvailable") == "1"]
    rows = rows[:15]
    if not rows:
        await inter.followup.send(f"No scores found for **{pos}**.")
        return
    players = await mfl.players()
    teams = await mfl.teams()
    owners = await mfl.owners()
    lines = []
    for i, r in enumerate(rows, 1):
        p = players.get(r["id"], {"name": f"Player #{r['id']}", "pos": pos, "team": ""})
        owner = teams.get(owners[r["id"]][0], "?") if r["id"] in owners else "🟢 FA"
        lines.append(f"**{i}. {p['name']}** ({p['team'] or 'FA'}) — "
                     f"**{float(r.get('score', 0)):.1f}** pts · {owner}")
    label = f"Week {week}" if week else f"{YEAR} Season"
    title = f"📊 Top {pos}s — {label}" + (" (Free Agents)" if available_only else "")
    await inter.followup.send(embed=discord.Embed(title=title, description="\n".join(lines),
                                                  color=GOLD))


# ---- /topscorers: best fantasy scores from one NFL game window -------------
# Game windows, decided by each game's kickoff time in US Central.
WINDOWS = {
    "tnf": "Thursday Night",
    "intl": "Sunday Morning (International)",
    "early": "Sunday Early",
    "late": "Sunday Late",
    "snf": "Sunday Night",
    "mnf": "Monday Night",
    "other": "Other (Fri/Sat/Holiday)",
}

# Positions shown by /topscorers, in display order. Team QB/K/P
# (TMQB/TMPK/TMPN) are left out on purpose.
SCORER_POS = ["RB", "WR", "TE", "DE", "DT", "LB", "CB", "S"]
TOP_N = 5  # players listed per position


def game_window(kickoff_unix):
    """Return the WINDOWS key for a game, from its kickoff (Unix seconds)."""
    k = datetime.fromtimestamp(int(kickoff_unix), CENTRAL)
    day, hour = k.strftime("%a"), k.hour
    if day == "Thu":
        return "tnf"
    if day == "Mon":
        return "mnf"
    if day == "Sun":
        if hour < 11:
            return "intl"      # London/Germany/etc. games, ~8:30am CT
        if hour < 14:
            return "early"     # noon CT
        if hour < 18:
            return "late"      # 3:05 / 3:25 CT
        return "snf"           # ~7:20pm CT
    return "other"             # Friday, Saturday, Christmas, etc.


@tree.command(name="topscorers", description="Top 5 scorers at each position from one NFL game window")
@app_commands.describe(window="Which games (TNF, Sunday early/late, SNF, MNF...)",
                       week="NFL week (leave blank for the current week)")
@app_commands.choices(window=[app_commands.Choice(name=n, value=k) for k, n in WINDOWS.items()])
async def topscorers(inter: discord.Interaction, window: app_commands.Choice[str],
                     week: app_commands.Range[int, 1, 18] = None):
    await inter.response.defer()

    # 1. NFL schedule for the week -> which teams play in this window.
    #    (nflSchedule has to come from api.myfantasyleague.com, not our league host.)
    params = {"W": str(week)} if week else {}
    sched = await mfl.get("nflSchedule", max_age=600, host=API_HOST, **params)
    sched = sched.get("nflSchedule", {})
    wk = sched.get("week", str(week or "?"))
    games, teams_in_window = [], set()
    for m in as_list(sched.get("matchup")):
        if game_window(m["kickoff"]) != window.value:
            continue
        sides = as_list(m.get("team"))
        away = next((t["id"] for t in sides if t.get("isHome") == "0"), sides[0]["id"])
        home = next((t["id"] for t in sides if t.get("isHome") == "1"), sides[-1]["id"])
        games.append(f"{away} @ {home}")
        teams_in_window.update(t["id"] for t in sides)

    if not games:
        await inter.followup.send(f"No **{window.name}** games in week {wk}.")
        return

    # 2. Weekly scores, grouped by position, keeping only players whose NFL
    #    team played in this window (and who actually scored).
    d = await mfl.get("playerScores", max_age=300, W=wk)
    players = await mfl.players()
    by_pos = {pos: [] for pos in SCORER_POS}
    for r in as_list(d.get("playerScores", {}).get("playerScore")):
        p = players.get(r["id"])
        if not p or p["team"] not in teams_in_window or p["pos"] not in by_pos:
            continue
        try:
            pts = float(r.get("score") or 0)
        except ValueError:
            continue
        if pts != 0:
            by_pos[p["pos"]].append((pts, r["id"], p))

    embed = discord.Embed(title=f"🔥 Top Scorers — Week {wk} · {window.name}",
                          description="**Games:** " + ", ".join(games), color=GOLD)
    if not any(by_pos.values()):
        embed.description += "\n\nNo points scored yet — these games may not have started."
        await inter.followup.send(embed=embed)
        return

    # 3. One section per position: top 5, highest first.
    teams = await mfl.teams()
    owners = await mfl.owners()
    for pos in SCORER_POS:
        rows = sorted(by_pos[pos], key=lambda x: x[0], reverse=True)[:TOP_N]
        if not rows:
            continue
        lines = []
        for i, (pts, pid, p) in enumerate(rows, 1):
            owner = teams.get(owners[pid][0], "?") if pid in owners else "🟢 FA"
            lines.append(f"{i}. **{p['name']}** ({p['team']}) — **{pts:.1f}** · {owner}")
        embed.add_field(name=pos, value="\n".join(lines)[:1024], inline=False)
    await inter.followup.send(embed=embed)


# ---- /rosteralerts: illegal roster / lineup check for every team ------------
# Injury statuses that mean "this player won't play" (Questionable/Doubtful are OK).
NOT_PLAYING = {"Out", "IR", "IR-R", "IR-PUP", "IR-NFI", "Suspended", "RETIRED", "Holdout"}


def parse_range(text):
    """MFL limit text "2-3" -> (2, 3); "1" -> (1, 1)."""
    lo, _, hi = str(text).partition("-")
    return int(lo), int(hi or lo)


def money(x):
    try:
        return float(x or 0)
    except ValueError:
        return 0.0


def team_payroll(fr, league, adjustments):
    """Salary that counts against the cap for one franchise:
    active salaries + the league's % of taxi/IR salaries + dead money."""
    taxi_pct = money(league.get("includeTaxiWithSalary") or 100) / 100
    ir_pct = money(league.get("includeIRWithSalary") or 100) / 100
    total = adjustments.get(fr["id"], 0.0)
    for e in as_list(fr.get("player")):
        st = e.get("status", "ROSTER")
        pct = taxi_pct if st == "TAXI_SQUAD" else ir_pct if st == "INJURED_RESERVE" else 1.0
        total += pct * money(e.get("salary"))
    return total


def find_violations(league, rosters, adjustments, lineups, players, injuries, bye_check_teams):
    """
    Check every team against the league's rules. Pure function (no network),
    so it is easy to test. Returns {franchise_id: [problem, ...]}.

    league         - the "league" export (rosterSize, taxiSquad, injuredReserve,
                     salaryCapAmount, includeTaxiWithSalary, includeIRWithSalary,
                     rosterLimits, starters)
    rosters        - list of franchises from the "rosters" export
    adjustments    - {franchise_id: total salary adjustments (dead money)}
    lineups        - {franchise_id: [starter ids]} for the week being checked;
                     pass {} to check roster rules only (no lineup checks)
    players        - mfl.players() dict
    injuries       - {player_id: status}
    bye_check_teams- set of NFL teams playing this week (empty = skip bye check)
    """
    max_active = int(league.get("rosterSize") or 0)
    max_taxi = int(league.get("taxiSquad") or 0)
    max_ir = int(league.get("injuredReserve") or 0)
    cap = money(league.get("salaryCapAmount"))

    # Roster position limits; "0-0" means no limit in MFL.
    pos_limits = {}
    for p in as_list((league.get("rosterLimits") or {}).get("position")):
        lo, hi = parse_range(p["limit"])
        if hi > 0:
            pos_limits[p["name"]] = (lo, hi)
    starters_cfg = league.get("starters") or {}
    start_total = int(starters_cfg.get("count") or 0)
    start_limits = {p["name"]: parse_range(p["limit"])
                    for p in as_list(starters_cfg.get("position"))}

    def pname(pid):
        p = players.get(pid)
        return f"{p['name']} ({p['pos']}, {p['team'] or 'FA'})" if p else f"Player #{pid}"

    out = {}
    for fr in rosters:
        fid, problems = fr["id"], []
        entries = as_list(fr.get("player"))
        status = {e["id"]: e.get("status", "ROSTER") for e in entries}
        active = [e for e in entries if e.get("status", "ROSTER") == "ROSTER"]
        taxi = [e for e in entries if e.get("status") == "TAXI_SQUAD"]
        ir = [e for e in entries if e.get("status") == "INJURED_RESERVE"]

        # --- Roster rules ---
        if max_active and len(active) > max_active:
            problems.append(f"🚨 Active roster has **{len(active)}** players (max {max_active})")
        if max_taxi and len(taxi) > max_taxi:
            problems.append(f"🚨 Taxi squad has **{len(taxi)}** players (max {max_taxi})")
        if max_ir and len(ir) > max_ir:
            problems.append(f"🚨 IR has **{len(ir)}** players (max {max_ir})")

        payroll = team_payroll(fr, league, adjustments)
        if cap and payroll > cap + 0.005:
            problems.append(f"🚨 Over the cap: **${payroll:,.2f}** (cap ${cap:,.2f}, "
                            f"over by ${payroll - cap:,.2f})")

        counts = {}
        for e in active:
            pos = players.get(e["id"], {}).get("pos", "?")
            counts[pos] = counts.get(pos, 0) + 1
        for pos, (lo, hi) in pos_limits.items():
            n = counts.get(pos, 0)
            if n > hi:
                problems.append(f"🚨 Rosters **{n} {pos}** (max {hi})")
            elif n < lo:
                problems.append(f"🚨 Rosters **{n} {pos}** (min {lo})")

        # --- This week's starting lineup ---
        starters = lineups.get(fid)
        if starters is not None:
            if start_total and len(starters) != start_total:
                problems.append(f"⚠️ Lineup has **{len(starters)}** starters "
                                f"(needs {start_total})")
            s_counts = {}
            for pid in starters:
                pos = players.get(pid, {}).get("pos", "?")
                s_counts[pos] = s_counts.get(pos, 0) + 1
            for pos, (lo, hi) in start_limits.items():
                n = s_counts.get(pos, 0)
                if n < lo or n > hi:
                    allowed = f"{lo}" if lo == hi else f"{lo}-{hi}"
                    problems.append(f"⚠️ Starting **{n} {pos}** (allowed {allowed})")
            for pid in starters:
                p = players.get(pid)
                st = status.get(pid)
                if st is None:
                    problems.append(f"⚠️ Starting {pname(pid)} — not on this roster")
                elif st == "TAXI_SQUAD":
                    problems.append(f"⚠️ Starting {pname(pid)} — on the taxi squad")
                elif st == "INJURED_RESERVE":
                    problems.append(f"⚠️ Starting {pname(pid)} — on IR")
                if p and p["team"] in ("", "FA"):
                    problems.append(f"⚠️ Starting {pname(pid)} — not on an NFL team")
                elif p and bye_check_teams and p["team"] not in bye_check_teams:
                    problems.append(f"⚠️ Starting {pname(pid)} — on bye")
                if injuries.get(pid) in NOT_PLAYING and st != "INJURED_RESERVE":
                    problems.append(f"⚠️ Starting {pname(pid)} — **{injuries[pid]}**")

        if problems:
            out[fid] = problems
    return out


async def build_roster_report(team=None, include_lineups=True):
    """
    Shared by /rosteralerts and /rosterviolations.
    team=None checks all teams; passing a team checks just that one (and adds
    its roster counts and cap room) – not used by a command right now.
    include_lineups=False -> only true roster violations (limits, cap, position limits).
    Always the CURRENT week: MFL only gives today's rosters and injuries,
    so checking an old week's lineups would flag players traded since.
    Returns (embeds, found) – also used by the Saturday lineup reminder.
    """
    teams = await mfl.teams()
    only = None
    if team:
        only = find_team(team, teams)
        if not only:
            return [discord.Embed(description=f"Couldn't find a team matching **{team}**.",
                                  color=GOLD)], {}

    league = (await mfl.get("league", max_age=3600))["league"]
    rosters = await mfl.rosters()
    players = await mfl.players()

    # Dead money / cap adjustments count toward the cap.
    adj = await mfl.get("salaryAdjustments", max_age=600)
    adjustments = {}
    for a in as_list((adj.get("salaryAdjustments") or {}).get("salaryAdjustment")):
        adjustments[a["franchise_id"]] = adjustments.get(a["franchise_id"], 0.0) + money(a.get("amount"))

    # Current week, and which NFL teams play (anyone else is on bye).
    sched = (await mfl.get("nflSchedule", max_age=600, host=API_HOST)).get("nflSchedule", {})
    wk = sched.get("week", "")
    playing = {t["id"] for m in as_list(sched.get("matchup")) for t in as_list(m.get("team"))}

    lineups, injuries = {}, {}
    if include_lineups:
        # Submitted starting lineups for this week.
        wr = await mfl.get("weeklyResults", max_age=300, W=wk)
        for m in as_list((wr.get("weeklyResults") or {}).get("matchup")):
            for f in as_list(m.get("franchise")):
                lineups[f["id"]] = [x for x in (f.get("starters") or "").split(",") if x]
        inj = await mfl.get("injuries", max_age=1800, host=API_HOST)
        injuries = {i["id"]: i.get("status", "")
                    for i in as_list((inj.get("injuries") or {}).get("injury"))}

    if only:
        rosters = [f for f in rosters if f["id"] == only]
    found = find_violations(league, rosters, adjustments, lineups, players, injuries, playing)

    scope = teams[only] if only else "All teams"
    if include_lineups:
        title = f"🚔 Roster Alerts — {scope} · Week {wk}"
        none_msg = "✅ No roster or lineup violations found."
        legend = "🚨 roster rule · ⚠️ this week's lineup (lineups can still change before kickoff)"
    else:
        title = f"🚨 Roster Violations — {scope}"
        none_msg = ("✅ Legal roster – within roster, taxi, IR, position and cap limits." if only else
                    "✅ No illegal rosters. Every team is within roster, taxi, IR, position and cap limits.")
        legend = "Roster rules only – see /rosteralerts for lineup issues"

    # Single team: show where they stand, even when they're legal.
    summary = ""
    if only and rosters:
        fr = rosters[0]
        sts = [e.get("status", "ROSTER") for e in as_list(fr.get("player"))]
        cap = money(league.get("salaryCapAmount"))
        pay = team_payroll(fr, league, adjustments)
        summary = (f"Active **{sts.count('ROSTER')}/{league.get('rosterSize')}** · "
                   f"Taxi **{sts.count('TAXI_SQUAD')}/{league.get('taxiSquad')}** · "
                   f"IR **{sts.count('INJURED_RESERVE')}/{league.get('injuredReserve')}**\n"
                   f"Cap **${pay:,.2f} / ${cap:,.2f}** "
                   f"({'over by' if pay > cap else 'room'} ${abs(cap - pay):,.2f})\n\n")

    if not found:
        return [discord.Embed(title=title, color=GOLD, description=summary + none_msg)], found

    # One block per team, packed into as few embeds/messages as Discord allows.
    blocks = [f"**{teams.get(fid, fid)}**\n" + "\n".join(f"• {p}" for p in probs)
              for fid, probs in sorted(found.items(), key=lambda x: teams.get(x[0], x[0]).lower())]
    embeds, cur = [], summary
    for b in blocks:
        b = b[:3900]
        if len(cur) + len(b) + 2 > 3900:
            embeds.append(cur)
            cur = ""
        cur += b + "\n\n"
    embeds.append(cur)
    embeds = [discord.Embed(description=e, color=GOLD) for e in embeds]
    embeds[0].title = title
    embeds[-1].set_footer(text=f"{len(found)} team(s) flagged · {legend}")
    return embeds, found


async def send_roster_report(inter, team=None, include_lineups=True):
    """Slash-command wrapper around build_roster_report()."""
    await inter.response.defer()
    embeds, _ = await build_roster_report(team, include_lineups)
    # Discord allows ~6000 characters per message, so send one embed per message.
    for e in embeds:
        await inter.followup.send(embed=e)


@tree.command(name="rosteralerts", description="All teams: roster AND this week's lineup problems (bye, injured, short lineups)")
async def rosteralerts(inter: discord.Interaction):
    await send_roster_report(inter, None, include_lineups=True)


@tree.command(name="rosterviolations", description="Illegal rosters only, all teams (roster/taxi/IR limits, cap, positions)")
async def rosterviolations(inter: discord.Interaction):
    await send_roster_report(inter, None, include_lineups=False)



# ---- /playoffs: playoff picture if the season ended today -----------------
# Blue Chip rules (league rule book, section 6):
#   * 12 teams make it; playoffs are Weeks 14-17.
#   * Seeds 1-4: the 4 division winners (best record in each division),
#     ordered by record, and they get a Week 14 bye.
#   * Seeds 5-12: the best remaining records.
#   * Brackets are reseeded so the highest seed always plays the lowest.
# Tiebreakers: we use MFL's own standings order (win %, points for,
# head-to-head, ...), which is how the league is set up on MFL.
PLAYOFF_TEAMS = 12
DIVISION_WINNERS = 4   # = number of divisions; these get byes
BUBBLE_SHOWN = 4       # teams listed as "first out"


def wlt(row):
    w, l, t = int(row.get("h2hw") or 0), int(row.get("h2hl") or 0), int(row.get("h2ht") or 0)
    return w, l, t


def record(row):
    w, l, t = wlt(row)
    return f"{w}-{l}" + (f"-{t}" if t else "")


def games_back(row, target):
    """Classic games-back: how far `row` trails `target` (ties count half)."""
    w, l, t = wlt(row)
    tw, tl, tt = wlt(target)
    return ((tw - w) + (l - tl)) / 2


def playoff_picture(standings, division_of):
    """
    standings   - leagueStandings rows, already in MFL's sorted order (best first)
    division_of - {franchise_id: division id}
    Returns (seeds, bubble): seeds = list of (seed, row, is_division_winner),
    bubble = the next BUBBLE_SHOWN rows after the last playoff spot.
    """
    winners, seen = [], set()
    for row in standings:                 # first team seen in each division = leader
        div = division_of.get(row["id"])
        if div not in seen:
            seen.add(div)
            winners.append(row)
        if len(winners) == DIVISION_WINNERS:
            break
    winner_ids = {r["id"] for r in winners}
    others = [r for r in standings if r["id"] not in winner_ids]
    wild = others[:PLAYOFF_TEAMS - len(winners)]
    seeds = [(i, r, True) for i, r in enumerate(winners, 1)]
    seeds += [(i, r, False) for i, r in enumerate(wild, len(winners) + 1)]
    bubble = others[len(wild):len(wild) + BUBBLE_SHOWN]
    return seeds, bubble


@tree.command(name="playoffs", description="Blue Chip playoff picture if the season ended today")
async def playoffs(inter: discord.Interaction):
    await inter.response.defer()
    teams = await mfl.teams()
    league = (await mfl.get("league", max_age=3600))["league"]
    division_of = {f["id"]: f.get("division")
                   for f in as_list(league["franchises"]["franchise"])}
    # Short division names: "Div 1 - SEC" -> "SEC"
    div_name = {d["id"]: d.get("name", d["id"]).split(" - ")[-1]
                for d in as_list((league.get("divisions") or {}).get("division"))}

    d = await mfl.get("leagueStandings", max_age=600)
    standings = as_list(d["leagueStandings"]["franchise"])
    seeds, bubble = playoff_picture(standings, division_of)
    if len(seeds) < PLAYOFF_TEAMS:
        await inter.followup.send("Not enough teams in the standings to build a playoff picture yet.")
        return

    def line(seed, row):
        name = teams.get(row["id"], row["id"])
        div = div_name.get(division_of.get(row["id"]), "")
        return (f"**{seed}. {name}** ({record(row)}) · "
                f"{float(row.get('pf') or 0):,.1f} PF · {div}")

    last_in = seeds[-1][1]
    embed = discord.Embed(title="🏈 Blue Chip Playoff Picture — if the season ended today",
                          url=LEAGUE_URL, color=GOLD)
    embed.add_field(name="🏆 Division winners · Week 14 bye",
                    value="\n".join(line(s, r) for s, r, _ in seeds[:DIVISION_WINNERS]),
                    inline=False)
    embed.add_field(name="🎟️ Wild cards",
                    value="\n".join(line(s, r) for s, r, _ in seeds[DIVISION_WINNERS:]),
                    inline=False)
    # Week 14 wild-card round: 5v12, 6v11, 7v10, 8v9
    wc = seeds[DIVISION_WINNERS:]
    games = [f"({wc[i][0]}) {teams.get(wc[i][1]['id'], '?')} vs "
             f"({wc[-1 - i][0]}) {teams.get(wc[-1 - i][1]['id'], '?')}"
             for i in range(len(wc) // 2)]
    embed.add_field(name="📅 Week 14 wild-card round", value="\n".join(games), inline=False)
    if bubble:
        out = []
        for row in bubble:
            gb = games_back(row, last_in)
            gb_txt = "tied" if gb <= 0 else f"{gb:g} GB"
            out.append(f"**{teams.get(row['id'], row['id'])}** ({record(row)}) · "
                       f"{float(row.get('pf') or 0):,.1f} PF · {gb_txt}")
        embed.add_field(name="🫧 First teams out (games back of the 12 seed)",
                        value="\n".join(out), inline=False)
    embed.set_footer(text="Division winners are seeds 1-4 by record; seeds 5-12 are the next-best records. "
                          "Ties use MFL standings order (win %, points for, head-to-head). "
                          "Reseeded each round.")
    await inter.followup.send(embed=embed)


# ---- /potentialpoints: PP rankings + draft lottery ------------------------
# Blue Chip rules (league rule book, section 14b): draft order for non-playoff
# teams is by Potential Points (PP). The 8 non-playoff teams with the LOWEST PP
# (draft ranks 25-32) go into a weighted lottery for picks 1.01-1.08:
#   lowest PP (rank 32) = 8 balls, next (31) = 7, ... rank 25 = 1 ball.
LOTTERY_TEAMS = 8


def lottery_balls(standings, playoff_ids):
    """{franchise_id: balls} for the 8 lowest-PP teams that aren't in the playoffs."""
    non_playoff = [r for r in standings if r["id"] not in playoff_ids]
    lowest = sorted(non_playoff, key=lambda r: money(r.get("pp")))[:LOTTERY_TEAMS]
    return {r["id"]: LOTTERY_TEAMS - i for i, r in enumerate(lowest)}


@tree.command(name="potentialpoints", description="Potential Points for all teams + draft lottery balls")
async def potentialpoints(inter: discord.Interaction):
    await inter.response.defer()
    teams = await mfl.teams()
    league = (await mfl.get("league", max_age=3600))["league"]
    division_of = {f["id"]: f.get("division")
                   for f in as_list(league["franchises"]["franchise"])}
    d = await mfl.get("leagueStandings", max_age=600)
    standings = as_list(d["leagueStandings"]["franchise"])

    # Who's in the playoffs today (same rules as /playoffs) - they can't be lottery teams.
    seeds, _ = playoff_picture(standings, division_of)
    seed_of = {r["id"]: s for s, r, _ in seeds}
    balls = lottery_balls(standings, set(seed_of))
    total_balls = sum(balls.values()) or 1

    # All teams, highest PP first, one per line.
    lines = []
    for i, r in enumerate(sorted(standings, key=lambda r: money(r.get("pp")), reverse=True), 1):
        name = teams.get(r["id"], r["id"])
        tag = ""
        if r["id"] in seed_of:
            tag = f" · 🎟️ #{seed_of[r['id']]} seed"
        elif r["id"] in balls:
            n = balls[r["id"]]
            tag = f" · 🎱 {n} lottery ball{'s' if n > 1 else ''}"
        lines.append(f"{i}. **{name}** — {money(r.get('pp')):,.1f} PP · "
                     f"{money(r.get('eff')):.1f}% eff · {record(r)}{tag}")

    embed = discord.Embed(title="📈 Blue Chip Potential Points", url=LEAGUE_URL,
                          description="\n".join(lines)[:4096], color=GOLD)

    # Lottery block: worst PP first, with odds of landing the 1.01 pick.
    lot = sorted(balls.items(), key=lambda x: x[1], reverse=True)
    lot_lines = []
    for fid, b in lot:
        r = next(x for x in standings if x["id"] == fid)
        lot_lines.append(f"🎱 **{b} ball{'s' if b > 1 else ''}** ({b / total_balls:.1%} for 1.01) — "
                         f"**{teams.get(fid, fid)}** · {money(r.get('pp')):,.1f} PP")
    if lot_lines:
        embed.add_field(name="🎱 Draft lottery if the season ended today (picks 1.01–1.08)",
                        value="\n".join(lot_lines)[:1024], inline=False)
    embed.set_footer(text="PP = points with a perfect lineup; eff = actual ÷ potential. "
                          "Lottery = 8 lowest-PP non-playoff teams (rule book §14b). "
                          "🎟️ = in the playoffs today (/playoffs).")
    await inter.followup.send(embed=embed)


# ---- /tradebait and /tradebaitall --------------------------------------------
# MFL "tradeBait" export, one entry per team that has posted:
#   franchise_id, willGiveUp (comma list of player ids / pick codes),
#   inExchangeFor (free text), timestamp (last update, Unix seconds).
# tradebait_embed() builds the one-team view. It is kept separate so the
# planned auto-checker (TODO #14) can post the same card whenever a team
# updates its trade bait.

def bait_asset(code, players, teams):
    """Readable text for one item a team will give up (player or pick)."""
    if code.startswith("FP_"):            # future pick: FP_franchise_year_round
        _, fr, yr, rd = code.split("_")
        return f"{yr} Round {rd} pick ({teams.get(fr, fr)})"
    if code.startswith("DP_"):            # current-year pick: DP_round_pick (0-based)
        _, rd, pk = code.split("_")
        return f"{YEAR} pick {int(rd) + 1}.{int(pk) + 1:02d}"
    p = players.get(code)
    return f"{p['name']} ({tag(p) or '?'})" if p else f"Player #{code}"


def bait_when(ts):
    try:
        return datetime.fromtimestamp(int(ts), CENTRAL).strftime("%b %d, %Y")
    except (TypeError, ValueError):
        return "unknown date"


async def trade_bait_entries():
    """{franchise_id: entry} for every team with trade bait posted."""
    d = await mfl.get("tradeBait", max_age=300)
    out = {}
    for b in as_list((d.get("tradeBaits") or {}).get("tradeBait")):
        items = [x for x in (b.get("willGiveUp") or "").split(",") if x]
        note = (b.get("inExchangeFor") or "").strip()
        if items or note:
            out[b["franchise_id"]] = {"items": items, "note": note, "ts": b.get("timestamp")}
    return out


def tradebait_embed(fid, entry, teams, players, roster_entries):
    """One team's trade bait as a Discord card, players grouped by position."""
    name = teams.get(fid, fid)
    embed = discord.Embed(title=f"🎣 Trade Bait — {name}", color=GOLD,
                          url=LEAGUE_URL)
    embed.description = (f"**Looking for:** {entry['note'] or '—'}\n"
                         f"Updated {bait_when(entry['ts'])}")
    contract = {e["id"]: e for e in roster_entries}
    groups = {}
    for code in entry["items"]:
        p = players.get(code)
        pos = "Picks" if code[:3] in ("FP_", "DP_") else (p["pos"] if p else "Other")
        line = bait_asset(code, players, teams)
        c = contract.get(code)
        if c and c.get("salary"):
            line += f" — ${money(c['salary']):,.2f}"
            # In this league contractInfo = YEARS REMAINING (contractYear = original length)
            if c.get("contractInfo"):
                line += f", {c['contractInfo']} yr left"
        groups.setdefault(pos, []).append(line)
    order = POS_ORDER + ["TMQB", "TMPK", "TMPN"]
    for pos in sorted(groups, key=lambda x: (order.index(x) if x in order else 99, x)):
        embed.add_field(name=pos, value="\n".join(groups[pos])[:1024], inline=False)
    if not entry["items"]:
        embed.add_field(name="Available", value="No specific players listed.", inline=False)
    embed.set_footer(text=f"{len(entry['items'])} player(s)/pick(s) on the block")
    return embed


@tree.command(name="tradebait", description="One team's trade bait from MFL")
@app_commands.describe(team="Start typing a team name")
@app_commands.autocomplete(team=team_autocomplete)
async def tradebait(inter: discord.Interaction, team: str):
    await inter.response.defer()
    teams = await mfl.teams()
    fid = find_team(team, teams)
    if not fid:
        await inter.followup.send(f"Couldn't find a team matching **{team}**.")
        return
    entries = await trade_bait_entries()
    if fid not in entries:
        await inter.followup.send(f"**{teams[fid]}** has no trade bait posted on MFL.")
        return
    players = await mfl.players()
    fr = next((f for f in await mfl.rosters() if f["id"] == fid), {})
    await inter.followup.send(embed=tradebait_embed(fid, entries[fid], teams, players,
                                                    as_list(fr.get("player"))))


@tree.command(name="tradebaitall", description="Every team's trade bait from MFL, most recently updated first")
async def tradebaitall(inter: discord.Interaction):
    await inter.response.defer()
    teams = await mfl.teams()
    entries = await trade_bait_entries()
    if not entries:
        await inter.followup.send("No teams have trade bait posted on MFL.")
        return
    players = await mfl.players()

    # One block per team, newest update first; players one per line.
    blocks = []
    for fid, e in sorted(entries.items(), key=lambda x: int(x[1]["ts"] or 0), reverse=True):
        lines = [f"**{teams.get(fid, fid)}** · updated {bait_when(e['ts'])}",
                 f"Looking for: {e['note'] or '—'}"]
        lines += [f"• {bait_asset(c, players, teams)}" for c in e["items"]]
        blocks.append("\n".join(lines))

    # Pack blocks into embeds (Discord: 4096 chars per embed description).
    chunks, cur = [], ""
    for b in blocks:
        b = b[:3900]
        if len(cur) + len(b) + 2 > 3900:
            chunks.append(cur)
            cur = ""
        cur += b + "\n\n"
    chunks.append(cur)
    embeds = [discord.Embed(description=c, color=GOLD) for c in chunks]
    embeds[0].title = f"🎣 Blue Chip Trade Bait — {len(entries)} teams"
    embeds[0].url = LEAGUE_URL
    embeds[-1].set_footer(text="From MFL trade bait. Use /tradebait for one team with salaries.")
    for e in embeds:                       # one embed per message (6000-char limit)
        await inter.followup.send(embed=e)


# ---- /ircheck: players on IR who are no longer IR-eligible -----------------
# Blue Chip rule book, section 4:
#   4b) Only players with an NFL injured-reserve designation on MFL can be on IR;
#       team positions (Team QB/K/P) can never be on IR.
#   4c) If a player's IR designation is lifted, he can't stay on IR - the owner
#       must activate him or cut him.
#   13h) Suspended players may also be put on IR.
IR_ELIGIBLE = {"IR", "IR-R", "IR-PUP", "IR-NFI", "Suspended"}
TEAM_POSITIONS = {"TMQB", "TMPK", "TMPN"}


def ir_ineligible(rosters, players, injuries):
    """{franchise_id: [(player_id, reason), ...]} for IR players who must come off IR."""
    out = {}
    for fr in rosters:
        for e in as_list(fr.get("player")):
            if e.get("status") != "INJURED_RESERVE":
                continue
            pid = e["id"]
            pos = players.get(pid, {}).get("pos", "")
            status = injuries.get(pid, "")
            if pos in TEAM_POSITIONS:
                reason = "team positions can never be on IR"
            elif status in IR_ELIGIBLE:
                continue                      # still eligible
            elif status:
                reason = f"listed **{status}**, not IR"
            else:
                reason = "no injury designation (healthy)"
            out.setdefault(fr["id"], []).append((pid, reason))
    return out


@tree.command(name="ircheck", description="All teams: players on IR who are no longer IR-eligible and must be activated or cut")
async def ircheck(inter: discord.Interaction):
    await inter.response.defer()
    teams = await mfl.teams()
    league = (await mfl.get("league", max_age=3600))["league"]
    rosters = await mfl.rosters()
    players = await mfl.players()
    inj = await mfl.get("injuries", max_age=1800, host=API_HOST)
    injuries = {i["id"]: i.get("status", "")
                for i in as_list((inj.get("injuries") or {}).get("injury"))}
    adj = await mfl.get("salaryAdjustments", max_age=600)
    adjustments = {}
    for a in as_list((adj.get("salaryAdjustments") or {}).get("salaryAdjustment")):
        adjustments[a["franchise_id"]] = adjustments.get(a["franchise_id"], 0.0) + money(a.get("amount"))

    found = ir_ineligible(rosters, players, injuries)
    title = "🚑 IR Eligibility Check — All teams"
    if not found:
        await inter.followup.send(embed=discord.Embed(
            title=title, color=GOLD,
            description="✅ Every player on IR has an IR (or suspension) designation."))
        return

    max_active = int(league.get("rosterSize") or 0)
    cap = money(league.get("salaryCapAmount"))
    ir_pct = money(league.get("includeIRWithSalary") or 100) / 100
    by_id = {f["id"]: f for f in rosters}

    blocks = []
    for fid, items in sorted(found.items(), key=lambda x: teams.get(x[0], x[0]).lower()):
        fr = by_id[fid]
        entries = {e["id"]: e for e in as_list(fr.get("player"))}
        lines = [f"**{teams.get(fid, fid)}**"]
        extra_salary = 0.0
        for pid, reason in items:
            p = players.get(pid)
            name = f"{p['name']} ({tag(p) or '?'})" if p else f"Player #{pid}"
            sal = money(entries.get(pid, {}).get("salary"))
            extra_salary += sal * (1 - ir_pct)    # cap hit goes from 25% to 100%
            lines.append(f"• {name} — {reason} · ${sal:,.2f}")
        # What happens if they activate everyone listed above?
        active_now = sum(1 for e in entries.values() if e.get("status", "ROSTER") == "ROSTER")
        active_after = active_now + len(items)
        pay_after = team_payroll(fr, league, adjustments) + extra_salary
        notes = [f"Active roster {active_now} → **{active_after}**/{max_active}"
                 + (f" (must cut {active_after - max_active})" if max_active and active_after > max_active else "")]
        notes.append(f"Cap after activating **${pay_after:,.2f}** / ${cap:,.2f}"
                     + (f" (**over by ${pay_after - cap:,.2f}**)" if pay_after > cap else
                        f" (room ${cap - pay_after:,.2f})"))
        lines.append("↳ " + " · ".join(notes))
        blocks.append("\n".join(lines))

    chunks, cur = [], ""
    for b in blocks:
        if len(cur) + len(b) + 2 > 3900:
            chunks.append(cur)
            cur = ""
        cur += b + "\n\n"
    chunks.append(cur)
    embeds = [discord.Embed(description=c, color=GOLD) for c in chunks]
    embeds[0].title = title
    total = sum(len(v) for v in found.values())
    embeds[-1].set_footer(text=f"{total} player(s) on {len(found)} team(s) must be activated or cut "
                               "(rule book §4b–c). Eligible: IR, IR-R, IR-PUP, IR-NFI, Suspended.")
    for e in embeds:
        await inter.followup.send(embed=e)


# ============================================================================
# Standard league reports: /recap, /matchups, /powerrankings, /capspace,
# /capnextyear, /owneractivity, /trades, and the Saturday lineup reminder.
# ============================================================================
import json as _json
from discord.ext import tasks

TEAM_POS = {"TMQB", "TMPK", "TMPN"}


def num(x):
    """MFL numbers come as strings (sometimes blank or with $) -> float."""
    try:
        return float(str(x or 0).replace("$", "").replace(",", "") or 0)
    except ValueError:
        return 0.0


async def current_week():
    """Current NFL week number from MFL's NFL schedule (e.g. 10)."""
    sched = (await mfl.get("nflSchedule", max_age=600, host=API_HOST)).get("nflSchedule", {})
    try:
        return int(sched.get("week"))
    except (TypeError, ValueError):
        return 1


async def week_games(week, played_only=True):
    """[(franchise a, franchise b)] for one week from weeklyResults.
    Each franchise dict has id, score, opt_pts, result. A team can appear twice
    in a doubleheader week. played_only drops games where both scores are 0."""
    d = await mfl.get("weeklyResults", max_age=300, W=str(week))
    out = []
    for m in as_list((d.get("weeklyResults") or {}).get("matchup")):
        fr = as_list(m.get("franchise"))
        if len(fr) != 2:
            continue
        if played_only and not (num(fr[0].get("score")) or num(fr[1].get("score"))):
            continue
        out.append((fr[0], fr[1]))
    return out


async def season_games(through_week):
    """[(week, a, b)] for every played regular-season game through a week."""
    league = (await mfl.get("league", max_age=3600))["league"]
    last = min(int(through_week), int(league.get("lastRegularSeasonWeek") or 13))
    out = []
    for w in range(1, last + 1):
        out += [(w, a, b) for a, b in await week_games(w)]
    return out


async def send_chunked(inter, title, blocks, footer=None, sep="\n"):
    """Send text blocks as one or more gold embeds (4,096 chars each)."""
    chunks, cur = [], ""
    for b in blocks:
        b = b[:3900]
        if len(cur) + len(b) + len(sep) > 3900:
            chunks.append(cur)
            cur = ""
        cur += b + sep
    chunks.append(cur)
    embeds = [discord.Embed(description=c, color=GOLD) for c in chunks]
    embeds[0].title = title
    embeds[0].url = LEAGUE_URL
    if footer:
        embeds[-1].set_footer(text=footer)
    for e in embeds:                       # one embed per message (6,000-char limit)
        await inter.followup.send(embed=e)


# ---- /recap ------------------------------------------------------------------
@tree.command(name="recap", description="Weekly recap: every result, high/low score, blowout, closest game, bench points")
@app_commands.describe(week="Week to recap (leave blank for last week)")
async def recap(inter: discord.Interaction, week: app_commands.Range[int, 1, 18] = None):
    await inter.response.defer()
    wk = week or max(1, await current_week() - 1)
    games = await week_games(wk)
    if not games:
        await inter.followup.send(f"No results for week {wk} yet.")
        return
    teams = await mfl.teams()
    name = lambda f: teams.get(f["id"], f["id"])

    # Results, highest winning score first.
    results = []
    for a, b in games:
        sa, sb = num(a.get("score")), num(b.get("score"))
        w, l = (a, b) if sa >= sb else (b, a)
        sw, sl = max(sa, sb), min(sa, sb)
        verb = "tied" if sa == sb else "def."
        results.append((sw, f"**{name(w)}** {sw:,.2f} {verb} {name(l)} {sl:,.2f} (+{sw - sl:,.2f})"))
    results.sort(key=lambda x: x[0], reverse=True)

    # Awards.
    sides = [(f, num(f.get("score")), num(f.get("opt_pts"))) for g in games for f in g]
    hi = max(sides, key=lambda x: x[1])
    lo = min(sides, key=lambda x: x[1])
    margins = [(abs(num(a.get("score")) - num(b.get("score"))), a, b) for a, b in games]
    blow = max(margins, key=lambda x: x[0])
    close = min(margins, key=lambda x: x[0])
    bench = max(sides, key=lambda x: x[2] - x[1])
    best_mgr = max(sides, key=lambda x: (x[1] / x[2]) if x[2] else 0)

    def game_txt(m):
        _, a, b = m
        sa, sb = num(a.get("score")), num(b.get("score"))
        w, l = (a, b) if sa >= sb else (b, a)
        return f"{name(w)} over {name(l)} by **{m[0]:,.2f}**"

    awards = [
        f"🔥 **High score:** {name(hi[0])} — {hi[1]:,.2f}",
        f"🧊 **Low score:** {name(lo[0])} — {lo[1]:,.2f}",
        f"💥 **Biggest blowout:** {game_txt(blow)}",
        f"😬 **Closest game:** {game_txt(close)}",
        f"🪑 **Most points left on the bench:** {name(bench[0])} — "
        f"{bench[2] - bench[1]:,.2f} (scored {bench[1]:,.2f} of a possible {bench[2]:,.2f})",
        f"🧠 **Best lineup:** {name(best_mgr[0])} — {best_mgr[1] / best_mgr[2]:.1%} of possible points",
    ]

    # Players of the week (offense and IDP), with their fantasy owner.
    d = await mfl.get("playerScores", max_age=600, W=str(wk), COUNT="400")
    players = await mfl.players()
    owners = await mfl.owners()
    best = {}
    idp = {"DE", "DT", "LB", "CB", "S"}
    for r in as_list((d.get("playerScores") or {}).get("playerScore")):
        p = players.get(r["id"])
        if not p or p["pos"] in TEAM_POS:
            continue
        side = "IDP" if p["pos"] in idp else "Offense"
        if side not in best or num(r.get("score")) > best[side][0]:
            best[side] = (num(r.get("score")), r["id"], p)
    for side in ("Offense", "IDP"):
        if side in best:
            pts, pid, p = best[side]
            owner = teams.get(owners[pid][0], "?") if pid in owners else "🟢 FA"
            awards.append(f"⭐ **{side} player of the week:** {p['name']} ({tag(p)}) — "
                          f"{pts:,.2f} · {owner}")

    embed = discord.Embed(title=f"📰 Week {wk} Recap", url=LEAGUE_URL, color=GOLD,
                          description="\n".join(r for _, r in results)[:4096])
    embed.add_field(name="🏅 Awards", value="\n".join(awards)[:1024], inline=False)
    await inter.followup.send(embed=embed)


# ---- /matchups ---------------------------------------------------------------
@tree.command(name="matchups", description="This week's matchups with records, points, playoff seeds and live scores")
@app_commands.describe(week="Week (leave blank for this week)")
async def matchups(inter: discord.Interaction, week: app_commands.Range[int, 1, 18] = None):
    await inter.response.defer()
    wk = week or await current_week()
    games = await week_games(wk, played_only=False)
    if not games:
        await inter.followup.send(f"No matchups found for week {wk}.")
        return
    teams = await mfl.teams()
    league = (await mfl.get("league", max_age=3600))["league"]
    division_of = {f["id"]: f.get("division") for f in as_list(league["franchises"]["franchise"])}
    standings = as_list((await mfl.get("leagueStandings", max_age=600))["leagueStandings"]["franchise"])
    row = {r["id"]: r for r in standings}
    seeds, _ = playoff_picture(standings, division_of)
    seed_of = {r["id"]: s for s, r, _ in seeds}
    last_in = seeds[-1][1] if seeds else None
    winners = {r["id"] for _, r, dw in seeds if dw}

    def on_bubble(fid):
        """Within about a game of the last playoff spot (in or out)."""
        if not last_in or fid in winners or fid not in row:
            return False
        return abs(games_back(row[fid], last_in)) <= 1.5

    def team_line(f):
        r = row.get(f["id"], {})
        s = seed_of.get(f["id"])
        where = f"🎟️ #{s} seed" if s else "out of playoffs"
        return (f"**{teams.get(f['id'], f['id'])}** · {record(r) if r else '?'} · "
                f"{num(r.get('pf')):,.1f} PF · {num(r.get('pp')):,.1f} PP · {where}")

    # Live scores for the current week (weeklyResults has no scores until the week is final).
    live = {}
    if wk == await current_week():
        ls = await mfl.get("liveScoring", max_age=120, W=str(wk))
        for m in as_list((ls.get("liveScoring") or {}).get("matchup")):
            for f in as_list(m.get("franchise")):
                live[f["id"]] = (num(f.get("score")), f.get("playersYetToPlay"))

    embed = discord.Embed(title=f"🏈 Week {wk} Matchups", url=LEAGUE_URL, color=GOLD)
    for a, b in games[:25]:
        flags = []
        if division_of.get(a["id"]) == division_of.get(b["id"]):
            flags.append("⚔️ Division game")
        if on_bubble(a["id"]) or on_bubble(b["id"]):
            flags.append("🔥 Playoff race")
        if a["id"] in live and b["id"] in live:
            (sa, ya), (sb, yb) = live[a["id"]], live[b["id"]]
            if sa or sb:
                flags.append(f"Live {sa:,.2f} – {sb:,.2f} (yet to play: {ya} / {yb})")
        else:
            sa, sb = num(a.get("score")), num(b.get("score"))
            if sa or sb:
                flags.append(f"Final {sa:,.2f} – {sb:,.2f}")
        value = team_line(a) + "\n" + team_line(b) + ("\n" + " · ".join(flags) if flags else "")
        embed.add_field(name=f"{teams.get(a['id'], a['id'])} vs {teams.get(b['id'], b['id'])}",
                        value=value[:1024], inline=False)
    embed.set_footer(text="🔥 = a team within ~1 game of the last playoff spot · seeds per /playoffs")
    await inter.followup.send(embed=embed)


# ---- /powerrankings ----------------------------------------------------------
@tree.command(name="powerrankings", description="Power rankings: all-play record, luck and recent form")
async def powerrankings(inter: discord.Interaction):
    await inter.response.defer()
    through = max(1, await current_week() - 1)          # completed weeks only
    games = await season_games(through)
    if not games:
        await inter.followup.send("No completed games yet.")
        return
    teams = await mfl.teams()
    st = {}
    by_week = {}
    for w, a, b in games:
        sa, sb = num(a.get("score")), num(b.get("score"))
        for me, s1, s2 in ((a, sa, sb), (b, sb, sa)):
            r = st.setdefault(me["id"], {"w": 0, "l": 0, "t": 0, "scores": [], "apw": 0, "apl": 0})
            r["scores"].append((w, s1))
            r["w" if s1 > s2 else "l" if s1 < s2 else "t"] += 1
            by_week.setdefault(w, []).append((me["id"], s1))
    # All-play: each week, your score vs every other team's score.
    for w, lst in by_week.items():
        for fid, s in lst:
            st[fid]["apw"] += sum(1 for o, so in lst if o != fid and s > so)
            st[fid]["apl"] += sum(1 for o, so in lst if o != fid and s < so)
    last_wk = max(by_week)
    recent_weeks = {last_wk - 2, last_wk - 1, last_wk}
    rows = []
    for fid, r in st.items():
        g = len(r["scores"])
        ap = r["apw"] / max(1, r["apw"] + r["apl"])
        recent = [s for w, s in r["scores"] if w in recent_weeks]
        rows.append({"fid": fid, "ap": ap, "apw": r["apw"], "apl": r["apl"],
                     "rec": f"{r['w']}-{r['l']}" + (f"-{r['t']}" if r["t"] else ""),
                     "luck": r["w"] - ap * g,
                     "recent": sum(recent) / len(recent) if recent else 0.0})
    rows.sort(key=lambda x: (x["ap"], x["recent"]), reverse=True)
    lines = [f"{i}. **{teams.get(x['fid'], x['fid'])}** — all-play {x['apw']}-{x['apl']} "
             f"({x['ap']:.3f}) · {x['rec']} · luck {x['luck']:+.1f} · last 3: {x['recent']:,.1f}/wk"
             for i, x in enumerate(rows, 1)]
    await send_chunked(inter, f"📊 Power Rankings — through Week {last_wk}", lines,
                       footer="All-play = record if you played every team every week. "
                              "Luck = actual wins minus all-play expected wins (+ = lucky). "
                              "Last 3 = average score over the last 3 weeks.")


# ---- /capspace ---------------------------------------------------------------
@tree.command(name="capspace", description="Every team's salary cap room this season, most room first")
async def capspace(inter: discord.Interaction):
    await inter.response.defer()
    teams = await mfl.teams()
    league = (await mfl.get("league", max_age=3600))["league"]
    cap = money(league.get("salaryCapAmount"))
    adj = await mfl.get("salaryAdjustments", max_age=600)
    adjustments = {}
    for a in as_list((adj.get("salaryAdjustments") or {}).get("salaryAdjustment")):
        adjustments[a["franchise_id"]] = adjustments.get(a["franchise_id"], 0.0) + money(a.get("amount"))
    rows = []
    for fr in await mfl.rosters():
        pay = team_payroll(fr, league, adjustments)
        active = sum(1 for e in as_list(fr.get("player")) if e.get("status", "ROSTER") == "ROSTER")
        rows.append((cap - pay, pay, active, fr["id"], adjustments.get(fr["id"], 0.0)))
    rows.sort(reverse=True)
    lines = []
    for i, (room, pay, active, fid, dead) in enumerate(rows, 1):
        flag = "🚨 " if room < 0 else ""
        lines.append(f"{i}. {flag}**{teams.get(fid, fid)}** — "
                     f"{'over by' if room < 0 else 'room'} **${abs(room):,.2f}** · "
                     f"${pay:,.2f} used · {active}/{league.get('rosterSize')} active"
                     + (f" · ${dead:,.2f} dead" if dead else ""))
    await send_chunked(inter, f"💰 Cap Space — {YEAR} (cap ${cap:,.2f})", lines,
                       footer="Cap used = active salaries + 25% of taxi/IR + dead money (matches MFL).")


# ---- /capnextyear ------------------------------------------------------------
@tree.command(name="capnextyear", description="Next season's cap after rollover: 20% raises, IR at 100%, expiring deals off")
async def capnextyear(inter: discord.Interaction):
    await inter.response.defer()
    import pitboss_ai                        # rollover rates live with the AI calculators
    raise_pct, cap_pct = pitboss_ai.SALARY_ESCALATION, pitboss_ai.CAP_ESCALATION
    teams = await mfl.teams()
    league = (await mfl.get("league", max_age=3600))["league"]
    cap_next = round(money(league.get("salaryCapAmount")) * (1 + cap_pct), 2)
    taxi_pct = money(league.get("includeTaxiWithSalary") or 100) / 100
    rows = []
    for fr in await mfl.rosters():
        total, kept, expiring_sal, expiring_n = 0.0, 0, 0.0, 0
        for e in as_list(fr.get("player")):
            left = int(e["contractInfo"]) if str(e.get("contractInfo") or "").isdigit() else 0
            sal = money(e.get("salary"))
            if left - 1 < 1:                 # contract ends after this season
                expiring_sal += sal
                expiring_n += 1
                continue
            # Rollover: +20% salary; IR counts 100% (everyone leaves IR by April 1); taxi stays 25%.
            pct = taxi_pct if e.get("status") == "TAXI_SQUAD" else 1.0
            total += sal * (1 + raise_pct) * pct
            kept += 1
        rows.append((cap_next - total, total, kept, expiring_n, expiring_sal, fr["id"]))
    rows.sort(reverse=True)
    lines = []
    for i, (room, total, kept, exp_n, exp_sal, fid) in enumerate(rows, 1):
        flag = "🚨 " if room < 0 else ""
        lines.append(f"{i}. {flag}**{teams.get(fid, fid)}** — "
                     f"{'over by' if room < 0 else 'room'} **${abs(room):,.2f}** · "
                     f"${total:,.2f} committed ({kept} players) · {exp_n} expiring (${exp_sal:,.2f} now)")
    nxt = int(YEAR) + 1
    await send_chunked(inter, f"🔮 {nxt} Cap Outlook (cap ${cap_next:,.2f})", lines,
                       footer=f"Rollover per rule book: salaries +{raise_pct:.0%}, cap +{cap_pct:.0%}, "
                              "IR players at 100%, taxi 25%, contracts with 1 year left drop off. "
                              "Not included: next year's dead money, tags, holdouts, rookie picks.")


# ---- /owneractivity (commissioners) -------------------------------------------
INACTIVE_DAYS = 7          # flag owners who haven't visited MFL in this many days


@tree.command(name="owneractivity", description="Commissioners: when each owner last visited the MFL site")
@app_commands.default_permissions(manage_guild=True)   # admins only by default; change in Server Settings > Integrations
async def owneractivity(inter: discord.Interaction):
    await inter.response.defer(ephemeral=True)
    teams = await mfl.teams()
    if mfl.session is None:
        mfl.session = aiohttp.ClientSession(headers={"User-Agent": USER_AGENT})
    url = f"{HOST}/fflnetdynamic{YEAR}/{LEAGUE_ID}_visitors.xml?random={int(time.time() // 60)}"
    async with mfl.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
        xml = await r.text()
    seen = {}
    for attrs in re.findall(r"<visit\s+([^>]*?)/>", xml):
        a = dict(re.findall(r'(\w+)="([^"]*)"', attrs))
        if a.get("franchise_id") in teams:
            seen[a["franchise_id"]] = int(a.get("timestamp") or 0)
    now = time.time()

    def ago(ts):
        mins = int((now - ts) // 60)
        if mins < 60:
            return f"{mins} min ago"
        if mins < 48 * 60:
            return f"{mins // 60} hr ago"
        return f"{mins // 1440} days ago"

    rows = sorted(((ts, fid) for fid, ts in seen.items()))        # longest away first
    lines = [f"{'⚠️ ' if now - ts > INACTIVE_DAYS * 86400 else ''}**{teams[fid]}** — {ago(ts)}"
             for ts, fid in rows]
    never = [teams[fid] for fid in teams if fid not in seen]
    lines += [f"⚠️ **{n}** — no recent visit recorded" for n in never]
    inactive = sum(1 for ts, _ in rows if now - ts > INACTIVE_DAYS * 86400) + len(never)
    embed = discord.Embed(title="👀 Owner Activity — last visit to MFL", color=GOLD,
                          description="\n".join(lines)[:4096])
    embed.set_footer(text=f"{inactive} owner(s) away more than {INACTIVE_DAYS} days (⚠️). "
                          "Only you can see this reply.")
    await inter.followup.send(embed=embed, ephemeral=True)


# ---- /trades -----------------------------------------------------------------
@tree.command(name="trades", description="Recent trades, plus how many trades each team has made this league year")
@app_commands.describe(days="How many days back to list (default 14)")
async def trades(inter: discord.Interaction, days: app_commands.Range[int, 1, 365] = 14):
    await inter.response.defer()
    teams = await mfl.teams()
    players = await mfl.players()
    d = await mfl.get("transactions", max_age=300, TRANS_TYPE="TRADE")    # whole league year
    all_trades = [t for t in as_list((d.get("transactions") or {}).get("transaction"))
                  if t.get("type") == "TRADE"]
    cutoff = time.time() - days * 86400
    recent = sorted((t for t in all_trades if int(t.get("timestamp") or 0) >= cutoff),
                    key=lambda t: int(t.get("timestamp") or 0), reverse=True)
    items = lambda s: [x for x in (s or "").split(",") if x]

    blocks = []
    for t in recent:
        a, b = t.get("franchise"), t.get("franchise2")
        when = datetime.fromtimestamp(int(t["timestamp"]), CENTRAL).strftime("%b %d")
        gets_a = [bait_asset(x, players, teams) for x in items(t.get("franchise2_gave_up"))]
        gets_b = [bait_asset(x, players, teams) for x in items(t.get("franchise1_gave_up"))]
        lines = [f"**{when}** · {teams.get(a, a)} ⇄ {teams.get(b, b)}"
                 + (" · *by commissioner*" if t.get("by_commish") == "1" else "")]
        lines += [f"**{teams.get(a, a)}** gets:"] + [f"• {x}" for x in gets_a or ["nothing"]]
        lines += [f"**{teams.get(b, b)}** gets:"] + [f"• {x}" for x in gets_b or ["nothing"]]
        if t.get("comments"):
            lines.append(f"📝 {t['comments']}")
        blocks.append("\n".join(lines))
    if not blocks:
        blocks = [f"No trades in the last {days} days."]

    # Season trade counts per team (every trade in MFL's league year).
    count = {fid: 0 for fid in teams}
    for t in all_trades:
        for fid in (t.get("franchise"), t.get("franchise2")):
            if fid in count:
                count[fid] += 1
    count_lines = [f"{i}. **{teams[fid]}** — {n}"
                   for i, (fid, n) in enumerate(sorted(count.items(), key=lambda x: (-x[1], teams[x[0]].lower())), 1)]
    await send_chunked(inter, f"🔁 Trades — last {days} days ({len(recent)})", blocks, sep="\n\n")
    await send_chunked(inter, f"📈 Trades per team — {YEAR} league year ({len(all_trades)} total)",
                       count_lines, footer="Counts every trade on MFL this league year, "
                                           "including commissioner-processed ones.")


# ---- Saturday lineup reminder (posts /rosteralerts automatically) -------------
LINEUP_REMINDER_ON = True
LINEUP_REMINDER_CHANNEL = "league-activity"   # channel name to post in
LINEUP_REMINDER_DAY = 5                        # 0 = Monday ... 5 = Saturday
LINEUP_REMINDER_HOUR = 19                      # 7 PM US Central
REMINDER_STATE = HERE / "data" / "lineup_reminder.json"   # remembers the last post date


def _reminder_last():
    try:
        return _json.loads(REMINDER_STATE.read_text()).get("last")
    except Exception:
        return None


def _reminder_save(day):
    REMINDER_STATE.parent.mkdir(exist_ok=True)
    REMINDER_STATE.write_text(_json.dumps({"last": day}))


async def post_lineup_reminder(force=False):
    """Post Roster Alerts to LINEUP_REMINDER_CHANNEL. Returns how many channels got it."""
    now = datetime.now(CENTRAL)
    today = now.strftime("%Y-%m-%d")
    if not force:
        if (now.weekday() != LINEUP_REMINDER_DAY or now.hour != LINEUP_REMINDER_HOUR
                or _reminder_last() == today):
            return 0
        league = (await mfl.get("league", max_age=3600))["league"]
        if await current_week() > int(league.get("endWeek") or 17):
            return 0                                   # season's over
    embeds, found = await build_roster_report(None, include_lineups=True)
    sent = 0
    for guild in client.guilds:
        ch = discord.utils.get(guild.text_channels, name=LINEUP_REMINDER_CHANNEL)
        if not ch:
            continue
        intro = ("⏰ **Lineup check before Sunday's games!** Fix these before kickoff."
                 if found else "⏰ **Lineup check:** every lineup looks good for Sunday. 👍")
        await ch.send(intro)
        for e in embeds:
            await ch.send(embed=e)
        sent += 1
    if sent:
        _reminder_save(today)
    return sent


@tasks.loop(minutes=5)
async def lineup_reminder_loop():
    try:
        await post_lineup_reminder()
    except Exception as e:                    # never let the loop die
        print("Lineup reminder error:", repr(e))


@lineup_reminder_loop.before_loop
async def _wait_ready():
    await client.wait_until_ready()


@tree.command(name="lineupreminder", description="Commissioners: post the Saturday lineup reminder now")
@app_commands.default_permissions(manage_guild=True)
async def lineupreminder(inter: discord.Interaction):
    await inter.response.defer(ephemeral=True)
    n = await post_lineup_reminder(force=True)
    await inter.followup.send(f"Posted to #{LINEUP_REMINDER_CHANNEL} in {n} server(s)." if n else
                              f"Couldn't find a #{LINEUP_REMINDER_CHANNEL} channel.", ephemeral=True)


@tree.error
async def on_error(inter: discord.Interaction, error):
    print("Command error:", repr(error))
    msg = "🎲 The Pit Boss hit a snag pulling that from MFL. Try again in a minute."
    try:
        if inter.response.is_done():
            await inter.followup.send(msg, ephemeral=True)
        else:
            await inter.response.send_message(msg, ephemeral=True)
    except Exception:
        pass


@client.event
async def on_ready():
    # Register the commands in each server instantly
    for guild in client.guilds:
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
    if LINEUP_REMINDER_ON and not lineup_reminder_loop.is_running():
        lineup_reminder_loop.start()       # Saturday lineup reminder (see above)
    print(f"Pit Boss is online as {client.user} in {len(client.guilds)} server(s). "
          f"Leave this window open.")


# ---- AI chat: @Pit Boss questions, personality, learning (see pitboss_ai.py) ----
import pitboss_ai
pitboss_ai.setup(client, tree, mfl, globals())

try:
    client.run(TOKEN)
except discord.errors.PrivilegedIntentsRequired:
    print("\n*** Pit Boss could not start: turn ON both 'Message Content Intent' and "
          "'Server Members Intent' in the Discord Developer Portal (your Pit Boss app > Bot > "
          "Privileged Gateway Intents), click Save Changes, then restart. ***\n")

