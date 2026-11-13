"""
Pit Boss - posts Blue Chip (MFL league 27743) trades and roster moves to Discord.

Runs on a schedule (GitHub Actions). Each run:
  1. Pulls recent transactions from MyFantasyLeague
  2. Skips anything it has already posted (remembered in state.json)
  3. Posts the new ones to the #league-activity Discord webhook

Settings come from GitHub "Secrets" (never put the webhook URL in this file):
  DISCORD_WEBHOOK_URL  - required
  MFL_API_KEY          - optional, only needed if the league is ever made private
"""

import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

# ---- League settings -------------------------------------------------------
LEAGUE_ID = "27743"
YEAR = "2026"
HOST = "https://www48.myfantasyleague.com"
LOOKBACK_DAYS = 7          # how far back to check each run
BOT_NAME = "Pit Boss"
STATE_FILE = "state.json"

# Which transaction types to post (others like LOCK_ALL_PLAYERS are ignored)
POST_TRADES = True
POST_ADDS_DROPS = True     # free agent pickups and waiver claims
POST_IR = False            # IR moves (set True if the league wants them)
POST_TAXI = False          # taxi squad moves

WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
API_KEY = os.environ.get("MFL_API_KEY", "").strip()
USER_AGENT = "PitBossDiscordBot/1.0 (Blue Chip league)"

CENTRAL = timezone(timedelta(hours=-6))  # display times in Central (CST)


# ---- Helpers ---------------------------------------------------------------
def mfl(type_, **params):
    params.update({"TYPE": type_, "L": LEAGUE_ID, "JSON": "1"})
    if API_KEY:
        params["APIKEY"] = API_KEY
    url = f"{HOST}/{YEAR}/export?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def ids(s):
    return [p for p in (s or "").split(",") if p]


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"seen": [], "initialized": False}


def save_state(state):
    state["seen"] = state["seen"][-1000:]  # keep the file small
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=1)


def key_for(t):
    return hashlib.sha1(json.dumps(t, sort_keys=True).encode()).hexdigest()[:16]


def post(embed):
    body = json.dumps({"username": BOT_NAME, "embeds": [embed]}).encode()
    req = urllib.request.Request(
        WEBHOOK, data=body, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    for attempt in range(3):
        try:
            urllib.request.urlopen(req, timeout=30)
            time.sleep(1.2)  # stay under Discord's rate limit
            return
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limited - wait and retry
                time.sleep(5)
                continue
            raise


# ---- Name lookups ----------------------------------------------------------
def franchise_names():
    data = mfl("league")
    return {f["id"]: f.get("name", f["id"])
            for f in as_list(data["league"]["franchises"]["franchise"])}


def player_names(player_ids):
    names = {}
    pid_list = sorted(set(player_ids))
    for i in range(0, len(pid_list), 50):
        chunk = pid_list[i:i + 50]
        data = mfl("players", PLAYERS=",".join(chunk))
        for p in as_list(data.get("players", {}).get("player")):
            raw = p.get("name", p["id"])
            if ", " in raw:  # MFL gives "Last, First"
                last, first = raw.split(", ", 1)
                raw = f"{first} {last}"
            extra = " ".join(x for x in [p.get("position"), p.get("team")] if x)
            names[p["id"]] = f"{raw} ({extra})" if extra else raw
    return names


def asset(a, players, teams):
    """Turn an MFL asset code into readable text."""
    if a.startswith("FP_"):  # future pick: FP_franchise_year_round
        _, fr, yr, rd = a.split("_")
        return f"{yr} Round {rd} pick ({teams.get(fr, fr)})"
    if a.startswith("DP_"):  # current-year pick: DP_round_pick (0-based)
        _, rd, pk = a.split("_")
        return f"{YEAR} pick {int(rd) + 1}.{int(pk) + 1:02d}"
    if a.startswith("BB_"):
        return f"${a[3:]} blind bid dollars"
    return players.get(a, f"Player #{a}")


# ---- Formatting ------------------------------------------------------------
def when(ts):
    return datetime.fromtimestamp(int(ts), CENTRAL).strftime("%a %b %d, %I:%M %p CT")


def format_txn(t, players, teams):
    typ = t.get("type")
    team = teams.get(t.get("franchise"), t.get("franchise"))

    if typ == "TRADE" and POST_TRADES:
        team2 = teams.get(t.get("franchise2"), t.get("franchise2"))
        got1 = [asset(a, players, teams) for a in ids(t.get("franchise2_gave_up"))]
        got2 = [asset(a, players, teams) for a in ids(t.get("franchise1_gave_up"))]
        title = "🤝 TRADE ALERT"
        if t.get("by_commish") == "1":
            title += " (processed by commish)"
        embed = {
            "title": title,
            "color": 0xF1C40F,
            "fields": [
                {"name": f"{team} receives", "value": "\n".join(got1) or "—", "inline": True},
                {"name": f"{team2} receives", "value": "\n".join(got2) or "—", "inline": True},
            ],
            "footer": {"text": when(t["timestamp"])},
        }
        if t.get("comments", "").strip():
            embed["description"] = f"💬 *{t['comments'].strip()}*"
        return embed

    if typ in ("FREE_AGENT", "WAIVER", "BBID_WAIVER") and POST_ADDS_DROPS:
        parts = (t.get("transaction") or "").split("|")
        added = ids(parts[0]) if parts else []
        if typ == "BBID_WAIVER":
            bid = parts[1] if len(parts) > 1 else ""
            dropped = ids(parts[2]) if len(parts) > 2 else []
        else:
            bid = ""
            dropped = ids(parts[1]) if len(parts) > 1 else []
        lines = [f"➕ **Added:** {players.get(p, f"Player #{p}")}" for p in added]
        if bid:
            lines[-1:] = [l + f" — ${bid} bid" for l in lines[-1:]]
        lines += [f"➖ **Dropped:** {players.get(p, f"Player #{p}")}" for p in dropped]
        label = {"FREE_AGENT": "Free Agent Move", "WAIVER": "Waiver Claim",
                 "BBID_WAIVER": "Blind Bid Waiver Won"}[typ]
        return {"title": f"📋 {label} — {team}", "description": "\n".join(lines),
                "color": 0x3498DB, "footer": {"text": when(t["timestamp"])}}

    if typ == "IR" and POST_IR:
        lines = [f"🚑 **To IR:** {players.get(p, f"Player #{p}")}" for p in ids(t.get("deactivated"))]
        lines += [f"✅ **Off IR:** {players.get(p, f"Player #{p}")}" for p in ids(t.get("activated"))]
        return {"title": f"IR Move — {team}", "description": "\n".join(lines),
                "color": 0xE74C3C, "footer": {"text": when(t["timestamp"])}}

    if typ == "TAXI" and POST_TAXI:
        lines = [f"🚕 **To taxi:** {players.get(p, f"Player #{p}")}" for p in ids(t.get("demoted"))]
        lines += [f"⬆️ **Promoted:** {players.get(p, f"Player #{p}")}" for p in ids(t.get("promoted"))]
        return {"title": f"Taxi Squad Move — {team}", "description": "\n".join(lines),
                "color": 0x95A5A6, "footer": {"text": when(t["timestamp"])}}

    return None


def player_ids_in(t):
    out = []
    for field in ("franchise1_gave_up", "franchise2_gave_up", "activated",
                  "deactivated", "promoted", "demoted"):
        out += [a for a in ids(t.get(field)) if a.isdigit()]
    for part in (t.get("transaction") or "").split("|"):
        out += [a for a in ids(part) if a.isdigit()]
    return out


# ---- Main ------------------------------------------------------------------
def main():
    if not WEBHOOK:
        sys.exit("DISCORD_WEBHOOK_URL secret is missing.")

    state = load_state()
    seen = set(state["seen"])

    data = mfl("transactions", DAYS=str(LOOKBACK_DAYS))
    txns = as_list(data.get("transactions", {}).get("transaction"))
    txns.sort(key=lambda t: int(t.get("timestamp", 0)))  # oldest first

    new = [t for t in txns if key_for(t) not in seen]

    # First run: don't flood the channel with old history - just say hello.
    if not state.get("initialized"):
        state["seen"] = [key_for(t) for t in txns]
        state["initialized"] = True
        save_state(state)
        post({"title": "🎰 The Pit Boss is on the floor",
              "description": "I'll post Blue Chip trades and roster moves here as they happen.",
              "color": 0x2ECC71})
        print(f"Initialized with {len(txns)} existing transactions.")
        return

    if not new:
        print("No new transactions.")
        return

    teams = franchise_names()
    pids = [p for t in new for p in player_ids_in(t)]
    players = player_names(pids) if pids else {}

    posted = 0
    for t in new:
        embed = format_txn(t, players, teams)
        if embed:
            post(embed)
            posted += 1
        state["seen"].append(key_for(t))
    save_state(state)
    print(f"Posted {posted} of {len(new)} new transactions.")


if __name__ == "__main__":
    main()
