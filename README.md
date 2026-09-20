# Time to Vote

A tiny local site for a Survivor pool, built for one shared touchscreen
laptop: each person taps their name card, then works through a tab per
question over a single always-visible grid of contestants — picks stay
ringed on-screen as they go, tabs can be revisited to change an answer, and
a Lock In button in the corner (with a confirmation, so nobody submits by
accident) locks everything in once every question is answered. Picks are
hashed on save so you can prove the data file wasn't edited after the fact.

The home page is just a row of cards — one per voting round, plus Demo,
Results, and Settings — there's no persistent nav bar; Results and Settings
each have a "← Home" link back to it.

## Running the actual event

- **`/demo`** — a walkthrough copy of the first round that never saves
  anything. Use it to show people how the tapping/locking flow works before
  the real thing starts.
- **`/kiosk/<round_id>`** (also linked as "Start Voting Session" from the
  home page) — the real thing. No navigation is shown at all, so nobody can
  wander off to `/results` and see someone else's picks; it's just an idle
  "tap to start" screen that loops back to itself after each person locks
  in, ready for the next voter. Tapping the idle screen also requests
  fullscreen. The only way out is a small, deliberately unobtrusive "exit"
  link in the bottom-right corner (confirms before leaving).
- **`/round/<round_id>`** — the same wizard without the kiosk wrapper, for
  voting from your own phone/laptop instead of the shared screen.

You'll do this at several points across the season — see **Voting
categories** below for the full planned breakdown — plus once with
`jury`, a special round that isn't in `rounds.json` at all. It's built
on the fly, one pick-1 question per jury member ("Who
did *Lewis* vote for?"), voting only among whoever's currently the final
3 (however many are still active once eliminations bring the cast down to
exactly 3) — so it automatically has no questions and stays gated behind a
"check back later" page until it's actually final-3 time. Mark someone as
a jury member when you record their vote-out in Settings (see below). The
home page shows how many are still in it and when it'll open; there's also
a testing override in Settings → History that opens it early with whoever's
currently active, for trying it out before the season's actually there.

## Voting categories

Live in `config/rounds.json`. Four rounds, each listed in the order it
should appear on screen (the marquee pick always last). "Any" questions
take as many picks as you like (at least 1); pick-2 questions with
**slots** label each pick in the order it was tapped:

**Pre-premiere** — blind, cast photos/bios only:
1. Most hated
2. Hottest contestant
3. First boot
4. First breakdown
5. Gives up / quits
6. Shot in the Dark — blind Sole Survivor guess

**Post-episode-1** — after watching the premiere; the marathon round:
1. Villains — any number
2. Dead weight / dragged along — any number
3. Butchers challenge — pick 2, slots: Puzzle, Physical
4. Challenge beast
5. Finds idol — pick 2 (plain)
6. Most episode titles
7. Blindside — pick 2, slots: Victim, Mastermind
8. Most votes against
9. Final Three — pick 3
10. Sole Survivor

**Merge** — re-picks plus merge-only categories; same votes-against →
final-three → Sole-Survivor order as post-episode-1, kept consistent
across every round that re-asks them:
1. Idol found and wasted
2. First jury member
3. Flips allegiance
4. Goat — final 3, fewest jury votes
5. Most votes against (re-pick)
6. Final Three (re-pick, pick 3)
7. Sole Survivor (re-pick)

**Jury** — unchanged: auto-built at final 3, one pick-1 question per jury
member.

## Run it

```bash
pip install -r requirements.txt
python main.py
```

Then open http://localhost:8000 on your laptop. Anyone on the same wifi can
hit it too at `http://<your-laptop-ip>:8000`.

## Running it on a Raspberry Pi, with a Cloudflare Tunnel

The plan is to leave this on a Pi and reach it from wherever the group's
watching (a friend's house, say) via a
[Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
instead of port-forwarding.

- **Keep it running** — a bare `python main.py` dies the moment you close
  the terminal. Run it as a systemd service so it starts on boot and comes
  back on its own if it ever crashes:

  ```ini
  # /etc/systemd/system/time-to-vote.service
  [Unit]
  Description=Time to Vote
  After=network.target

  [Service]
  WorkingDirectory=/home/pi/time-to-vote
  ExecStart=/home/pi/time-to-vote/.venv/bin/python main.py
  Restart=on-failure
  User=pi

  [Install]
  WantedBy=multi-user.target
  ```

  ```bash
  sudo systemctl enable --now time-to-vote
  ```

  Also flip `reload=True` to `False` in the `uvicorn.run(...)` call at the
  bottom of `main.py` first — the file-watcher it enables is a dev
  convenience, not something you want on a Pi running unattended.

- **The tunnel** — `cloudflared tunnel --url http://localhost:8000` hands
  you a throwaway `*.trycloudflare.com` URL each time you start it, which is
  fine for a one-off. For a link you can bookmark and reuse every season,
  set up a named tunnel instead (`cloudflared tunnel create`, point its
  config at `localhost:8000`, route a hostname to it) and install it as a
  service too (`cloudflared service install`) so it comes up alongside the
  app on boot.

- **Lock down `/admin` before you expose it** — Settings has no login at
  all (see below), which is fine on your own wifi but not once a tunnel
  puts it on the open internet. The clean fix is
  [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/policies/access/)
  in front of the tunnel (free for small teams) — it makes everyone
  one-time-code themselves in with email before they reach the site at all,
  admin included. The low-effort fix is to just only run `cloudflared`
  while you're actively at the watch party and kill it after.

## Configure

- `config/rounds.json` — the `pre_premiere`, `post_premiere`, and `merge` rounds (the `jury` round
  isn't here — see above). Each bundles several questions into one form
  that's filled out and locked in all at once. Add, remove, or reword
  questions here; the app builds the pages from this list. `pick_count`
  is a number (pick exactly N) or `"any"` (at least 1, no cap). A
  question can also set `"slots": ["Puzzle", "Physical"]` to label each
  pick by the order it was chosen. A question can also set `"color": "#hex"` to give it a fixed
  ring/tab color instead of the next one in the rotation — used for "Sole
  Survivor" (red, since they're on fire).
- `config/contestants.json` — the cast: id, name, `image` (a path under
  `static/`), and `tribes` — a list of tribe ids in the order this person
  has belonged to them, one if they've never swapped, two if they have. The
  tribe list shows up as a small colored bar at the bottom of their tile
  (separate from the colored rings, which track your picks). Easiest to
  manage through the Contestants tab in **`/admin`** rather than
  hand-editing — see `scripts/scrape_castaways.py` below for the fastest
  way to fill this in from scratch.
- `config/tribes.json` — the tribe roster (id, name, color). Rename,
  recolor, or add tribes from the Tribes tab in `/admin`, or hand-edit.
- `config/history.json` — the season's timeline: an ordered list of events,
  each either a vote-out (`"type": "vote_out"`, one or more contestant ids
  for double-boot nights) or a text marker (`"type": "text"`, e.g. "Tribe
  Swap" or "Merge"). Easiest to manage through **`/admin`** rather than
  hand-editing — see below. Voted-out contestants are automatically
  excluded from the pick grid so nobody can vote for someone who's already
  gone, and the whole timeline renders as a strip of cards (the one place
  in the app that scrolls) on `/results` and beneath the grid on any
  voting page once there's history to show. This file is gitignored (copy
  `config/history.example.json` to get started) since it's a running spoiler
  for anyone who hasn't watched yet.
- `config/players.json` — your friend group's names for the name-card
  picker. This file is gitignored (copy `config/players.example.json` to
  get started) so your friends' names don't end up in the public repo.

## Settings page

**`/admin`** ("Settings" on the home page) is a no-auth contestant-management
page — anyone on your network with the URL can use it, so it's really just
for whoever's running the laptop. It's split into three tabs:

- **Contestants** — assign a tribe to a contestant (their starting tribe,
  or a second one after a swap), or remove one you added by mistake.
- **History** — add a vote-out (check off everyone who went home that
  night — check more than one for a double boot; check "Jury member(s)" if
  this is jury phase, which is what feeds the `jury` round's roster) or an
  event like a challenge win, tribe swap, or idol find (check as many
  contestants as it applies to — everyone on the winning team, say), each
  with an optional episode number and note; remove an entry if you
  fat-fingered it. The jury round's testing override toggle lives here too.
- **Tribes** — rename and recolor a tribe, or add more.

## Seeding a new season

`scripts/scrape_castaways.py` fills in `config/contestants.json` and
`config/tribes.json` from a Survivor Fandom wiki season page (e.g.
`survivor.fandom.com/wiki/Survivor_51`), downloading each contestant's
photo to `static/images/contestants/` along the way — much faster than
typing 18-24 castaways in by hand every season.

```bash
pip install -r scripts/requirements.txt
python scripts/scrape_castaways.py https://survivor.fandom.com/wiki/Survivor_51
```

Fandom sits behind a Cloudflare bot challenge, so that direct fetch usually
gets blocked — the script will tell you so. When that happens: open the
page in your own browser, save it (Ctrl+S / Cmd+S → "Webpage, HTML only"),
and run the script again with `--html-file <saved.html>` instead of the
URL (photo downloads still work either way — they come from Fandom's
separate, unprotected image CDN). Add `--dry-run` to preview what it found
without writing or downloading anything.

This **overwrites** `contestants.json` and `tribes.json`, so review with
`git diff` before committing. Tribes aren't announced this early in a
season, so everyone comes out with `"tribes": []` — assign them from the
Contestants tab in `/admin` once they're revealed. Re-run it for each new
season; the castaways table layout has stayed consistent across seasons on
this wiki.

## Data & integrity

Locked-in submissions are saved to `data/<round>.json`, one file per round,
keyed by player name. Each record stores a SHA-256 hash of its own contents
(`player`, `round`, `answers`, `locked_at`). The `/results` page recomputes
that hash for every record and flags anything that doesn't match, so you
can tell if a data file was hand-edited after someone locked in.

This isn't meant to stop a determined attacker (the hash lives right next to
the data it protects) — it's just enough to catch accidental edits or prove
to your group that nobody quietly changed their picks after the season
started.

`data/` is gitignored — everyone's guesses stay local to whoever's running
the server.

## Scoring

Not built yet — the plan is 1 point for 1st boot, 2 for 2nd, etc., +1 per
elimination after the merge, with same-night boots scoring the same. Once
that's nailed down it can read straight from the `data/*.json` files.

## Ideas kicking around

Nothing here is planned, just noted for later:

- **A live standings page** — once scoring exists, a leaderboard that
  auto-refreshes (a `<meta refresh>` or a few lines of `setInterval` polling
  `/results`) so it can just sit up on a second screen during the watch
  party instead of someone manually reloading.
- **A QR code on the home page** — once this is behind a Cloudflare Tunnel
  the URL is a long random subdomain, not something anyone wants to type
  into their phone by hand for `/round/<id>`. A QR pointing at the current
  page would save that.
- **A vote-lock deadline per round** — close `start`/`merge` automatically
  at a set time (or just "episode N has aired") so nobody can sneak in a
  pick after seeing something that gives it away.
- **Idle timeout back to the kiosk idle screen** — if someone starts voting
  and walks off mid-round without locking in, the wizard just sits there
  open under their name until someone notices.
- **One-click backup** — a button in Settings that zips up `config/` and
  `data/` for download, so there's an off-Pi copy without SSHing in for it.
- **A PIN on `/admin`** — short of full Cloudflare Access, even a single
  shared PIN gate (one env var, one login form) would stop a stray tunnel
  link from letting anyone edit history or contestants.
