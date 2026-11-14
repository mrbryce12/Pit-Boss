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
import time
from pathlib import Path

import aiohttp
import discord
from discord import app_commands

# ---- League settings -------------------------------------------------------
LEAGUE_ID = "27743"
YEAR = "2026"
HOST = "https://www48.myfantasyleague.com"
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

    async def get(self, type_, max_age=300, **params):
        key = (type_, tuple(sorted(params.items())))
        hit = self.cache.get(key)
        if hit and time.time() - hit[0] < max_age:
            return hit[1]
        if self.session is None:
            self.session = aiohttp.ClientSession(headers={"User-Agent": USER_AGENT})
        q = {"TYPE": type_, "L": LEAGUE_ID, "JSON": "1", **params}
        if API_KEY:
            q["APIKEY"] = API_KEY
        async with self.session.get(f"{HOST}/{YEAR}/export", params=q,
                                    timeout=aiohttp.ClientTimeout(total=30)) as r:
            data = await r.json(content_type=None)
        self.cache[key] = (time.time(), data)
        return data

    async def teams(self):
        d = await self.get("league", max_age=86400)
        return {f["id"]: f.get("name", f["id"])
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
