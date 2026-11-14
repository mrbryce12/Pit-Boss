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
        if e.get("contractYear"):
            extra.append(f"{e['contractYear']} yr")
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
        if entry.get("contractYear"):
            embed.add_field(name="Contract", value=f"{entry['contractYear']} yr", inline=True)
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


async def send_roster_report(inter, team=None, include_lineups=True):
    """
    Shared by /rosteralerts and /rosterviolations.
    team=None checks all teams; passing a team checks just that one (and adds
    its roster counts and cap room) – not used by a command right now.
    include_lineups=False -> only true roster violations (limits, cap, position limits).
    Always the CURRENT week: MFL only gives today's rosters and injuries,
    so checking an old week's lineups would flag players traded since.
    """
    await inter.response.defer()
    teams = await mfl.teams()
    only = None
    if team:
        only = find_team(team, teams)
        if not only:
            await inter.followup.send(f"Couldn't find a team matching **{team}**.")
            return

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
        await inter.followup.send(embed=discord.Embed(
            title=title, color=GOLD, description=summary + none_msg))
        return

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
    print(f"Pit Boss is online as {client.user} in {len(client.guilds)} server(s). "
          f"Leave this window open.")


client.run(TOKEN)
