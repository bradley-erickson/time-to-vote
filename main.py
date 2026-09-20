import json
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import utils

BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"

app = FastAPI(title="Time to Vote")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.filters["to_json"] = json.dumps


def load_config(name: str):
    path = CONFIG_DIR / name
    if not path.exists():
        path = CONFIG_DIR / name.replace(".json", ".example.json")
    return json.loads(path.read_text())


def save_config(name: str, data):
    (CONFIG_DIR / name).write_text(json.dumps(data, indent=2) + "\n")


def get_rounds():
    return load_config("rounds.json")


def get_round(round_id: str):
    return next((r for r in get_rounds() if r["id"] == round_id), None)


def get_tribes():
    return load_config("tribes.json")


def get_tribes_by_id():
    return {t["id"]: t for t in get_tribes()}


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or uuid.uuid4().hex[:6]


def get_contestants():
    """Contestants grouped by current tribe (the tribes.json order), then
    by original tribe within that group, then by name — so swaps cluster
    people with their new tribemates while keeping old allies together."""
    tribes = get_tribes_by_id()
    tribe_order = {tid: i for i, tid in enumerate(tribes)}
    no_tribe = len(tribe_order)
    contestants = load_config("contestants.json")
    for c in contestants:
        assigned = [tribes[t] for t in c.get("tribes", []) if t in tribes]
        c["tribe_colors"] = [t["color"] for t in assigned]
        c["tribe_names"] = [t["name"] for t in assigned]
        c["first_name"] = c["name"].split(" ", 1)[0]

    def sort_key(c):
        tribe_ids = [t for t in c.get("tribes", []) if t in tribe_order]
        current = tribe_order[tribe_ids[-1]] if tribe_ids else no_tribe
        original = tribe_order[tribe_ids[0]] if tribe_ids else no_tribe
        return (current, original, c["name"])

    contestants.sort(key=sort_key)
    return contestants


def get_history():
    return load_config("history.json")


def get_eliminated_ids():
    """Contestant ids that have appeared in any vote_out event, in the
    order they were first voted out."""
    ids = []
    for event in get_history():
        if event.get("type") == "vote_out":
            for cid in event.get("contestants", []):
                if cid not in ids:
                    ids.append(cid)
    return ids


def get_active_contestants():
    eliminated = set(get_eliminated_ids())
    return [c for c in get_contestants() if c["id"] not in eliminated]


def get_jury_ids():
    """Contestant ids from vote_out events marked as jury, in the order
    they joined the jury."""
    ids = []
    for event in get_history():
        if event.get("type") == "vote_out" and event.get("jury"):
            for cid in event.get("contestants", []):
                if cid not in ids:
                    ids.append(cid)
    return ids


def get_jury_contestants():
    contestants = {c["id"]: c for c in get_contestants()}
    return [contestants[cid] for cid in get_jury_ids() if cid in contestants]


def get_settings():
    return load_config("settings.json")


def get_finalists():
    """The final 3, once eliminations have narrowed the cast down that far
    — or, with the testing override on, whoever's currently active."""
    active = get_active_contestants()
    if get_settings().get("jury_override"):
        return active
    return active if len(active) == 3 else []


def get_jury_round():
    """A round definition built on the fly: one pick-1 question per jury
    member, asking who they voted for at the final tribal council."""
    active = get_active_contestants()
    finalists = get_finalists()
    override = get_settings().get("jury_override")
    if finalists:
        status = "Testing override is on — ready to vote." if override else "Final 3 reached — ready to vote!"
    else:
        status = f"{len(active)} still in it — opens once we're down to the final 3."
    questions = [
        {"id": j["id"], "prompt": f"Who did {j['first_name']} vote for?", "pick_count": 1, "icon": "person-fill"}
        for j in get_jury_contestants()
    ]
    return {
        "id": "jury",
        "title": "Jury Predictions",
        "subtitle": "Fill this out once, after we're down to the final 3.",
        "questions": questions,
        "status": status,
    }


def resolve_round(round_id: str):
    if round_id == "jury":
        return get_jury_round()
    return get_round(round_id)


def contestants_for_round(round_id: str):
    if round_id == "jury":
        return get_finalists()
    return get_active_contestants()


def resolve_history():
    """History events with each vote_out event's contestant ids swapped
    for the full contestant record, ready for the timeline templates."""
    contestants = {c["id"]: c for c in get_contestants()}
    resolved = []
    for event in get_history():
        entry = dict(event)
        entry["contestants"] = [
            contestants[cid] for cid in event.get("contestants", []) if cid in contestants
        ]
        resolved.append(entry)
    return resolved


def get_players():
    return load_config("players.json")


@app.get("/")
def home(request: Request):
    rounds = get_rounds() + [get_jury_round()]
    locked_by_round = {r["id"]: sorted(utils.load_submissions(r["id"]).keys()) for r in rounds}
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "rounds": rounds,
            "locked_by_round": locked_by_round,
            "players": get_players(),
        },
    )


@app.get("/round/{round_id}")
def round_form(request: Request, round_id: str):
    round_ = resolve_round(round_id)
    if not round_:
        return RedirectResponse("/")
    if round_id == "jury" and not get_finalists():
        return templates.TemplateResponse(request, "not_ready.html", {"round": round_})
    submissions = utils.load_submissions(round_id)
    return templates.TemplateResponse(
        request,
        "round.html",
        {
            "round": round_,
            "contestants": contestants_for_round(round_id),
            "history": resolve_history(),
            "players": get_players(),
            "locked_players": sorted(submissions.keys()),
            "mode": "demo" if request.query_params.get("demo") else "normal",
            "submit_url": f"/round/{round_id}",
        },
    )


@app.get("/demo")
def demo(request: Request):
    round_ = get_rounds()[0]
    return templates.TemplateResponse(
        request,
        "round.html",
        {
            "round": round_,
            "contestants": get_active_contestants(),
            "history": resolve_history(),
            "players": get_players(),
            "locked_players": [],
            "mode": "demo",
            "submit_url": "",
        },
    )


@app.get("/kiosk/{round_id}")
def kiosk(request: Request, round_id: str):
    round_ = resolve_round(round_id)
    if not round_:
        return RedirectResponse("/")
    if round_id == "jury" and not get_finalists():
        return templates.TemplateResponse(request, "not_ready.html", {"round": round_})
    submissions = utils.load_submissions(round_id)
    return templates.TemplateResponse(
        request,
        "kiosk.html",
        {
            "round": round_,
            "contestants": contestants_for_round(round_id),
            "history": resolve_history(),
            "players": get_players(),
            "locked_players": sorted(submissions.keys()),
            "mode": "kiosk",
            "submit_url": f"/round/{round_id}",
        },
    )


@app.post("/round/{round_id}")
async def submit_round(request: Request, round_id: str):
    round_ = resolve_round(round_id)
    if not round_:
        return JSONResponse({"error": "Unknown round."}, status_code=404)

    form = await request.form()
    player = (form.get("player") or "").strip()

    submissions = utils.load_submissions(round_id)
    answers = {}
    error = None

    if not player:
        error = "Pick your name first."
    elif player not in get_players():
        error = "Unknown player."
    elif player in submissions:
        error = f"{player} already locked in {round_['title']}."
    else:
        for question in round_["questions"]:
            picks = form.getlist(f"answer__{question['id']}")
            if question["pick_count"] == "any":
                if not picks:
                    error = f"\"{question['prompt']}\" needs at least 1 pick."
                    break
            elif len(picks) != question["pick_count"]:
                error = f"\"{question['prompt']}\" needs exactly {question['pick_count']} pick(s)."
                break
            answers[question["id"]] = picks

    if error:
        return JSONResponse({"error": error}, status_code=400)

    record = utils.save_submission(round_id, player, answers)
    return JSONResponse({"ok": True, "player": player, "locked_at": record["locked_at"]})


@app.get("/results")
def results(request: Request):
    rounds = get_rounds() + [get_jury_round()]
    contestants = {c["id"]: c for c in get_contestants()}
    data = {}
    for r in rounds:
        submissions = utils.load_submissions(r["id"])
        rows = []
        for player, record in sorted(submissions.items()):
            answer_rows = [
                {
                    "prompt": q["prompt"],
                    "picks": [
                        contestants.get(pid, {"id": pid, "name": pid, "first_name": pid, "image": None})
                        for pid in record["answers"].get(q["id"], [])
                    ],
                }
                for q in r["questions"]
            ]
            rows.append(
                {
                    "player": player,
                    "answers": answer_rows,
                    "locked_at": record["locked_at"],
                    "verified": utils.verify_submission(r["id"], player, record),
                }
            )
        data[r["id"]] = rows
    return templates.TemplateResponse(
        request, "results.html", {"rounds": rounds, "data": data, "history": resolve_history()}
    )


@app.get("/admin")
def admin_page(request: Request):
    active_tab = request.query_params.get("tab", "history")
    if active_tab not in ("history", "contestants", "tribes", "players"):
        active_tab = "history"
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "active_tab": active_tab,
            "contestants": get_contestants(),
            "tribes": get_tribes(),
            "active_contestants": get_active_contestants(),
            "history": resolve_history(),
            "players": get_players(),
            "jury_override": get_settings().get("jury_override", False),
        },
    )


@app.post("/admin/history/add")
async def admin_add_history(request: Request):
    form = await request.form()
    event_type = form.get("type")
    note = (form.get("note") or "").strip() or None
    episode_raw = (form.get("episode") or "").strip()
    episode = int(episode_raw) if episode_raw.isdigit() else None

    history = get_history()
    if event_type == "vote_out":
        contestants = form.getlist("contestants")
        jury = form.get("jury") == "on"
        if contestants:
            history.append(
                {
                    "id": uuid.uuid4().hex[:8],
                    "type": "vote_out",
                    "contestants": contestants,
                    "label": None,
                    "note": note,
                    "episode": episode,
                    "jury": jury,
                }
            )
    else:
        label = (form.get("label") or "").strip()
        contestants = form.getlist("contestants")
        if label:
            history.append(
                {
                    "id": uuid.uuid4().hex[:8],
                    "type": "text",
                    "contestants": contestants,
                    "label": label,
                    "note": note,
                    "episode": episode,
                }
            )
    save_config("history.json", history)
    return RedirectResponse("/admin?tab=history", status_code=303)


@app.post("/admin/history/delete")
async def admin_delete_history(request: Request):
    form = await request.form()
    event_id = form.get("id")
    history = [e for e in get_history() if e.get("id") != event_id]
    save_config("history.json", history)
    return RedirectResponse("/admin?tab=history", status_code=303)


@app.post("/admin/tribes/add")
async def admin_add_tribe(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    color = (form.get("color") or "").strip()
    if name and color:
        tribes = get_tribes()
        existing_ids = {t["id"] for t in tribes}
        tribe_id = slugify(name)
        while tribe_id in existing_ids:
            tribe_id = f"{tribe_id}-{uuid.uuid4().hex[:4]}"
        tribes.append({"id": tribe_id, "name": name, "color": color})
        save_config("tribes.json", tribes)
    return RedirectResponse("/admin?tab=tribes", status_code=303)


@app.post("/admin/tribes/update")
async def admin_update_tribe(request: Request):
    form = await request.form()
    tribe_id = form.get("id")
    name = (form.get("name") or "").strip()
    color = (form.get("color") or "").strip()
    tribes = get_tribes()
    for t in tribes:
        if t["id"] == tribe_id:
            if name:
                t["name"] = name
            if color:
                t["color"] = color
    save_config("tribes.json", tribes)
    return RedirectResponse("/admin?tab=tribes", status_code=303)


@app.post("/admin/contestants/{contestant_id}/add_tribe")
async def admin_add_contestant_tribe(request: Request, contestant_id: str):
    form = await request.form()
    tribe_id = form.get("tribe_id")
    tribes = get_tribes_by_id()
    if tribe_id in tribes:
        contestants = load_config("contestants.json")
        for c in contestants:
            if c["id"] == contestant_id:
                c.setdefault("tribes", []).append(tribe_id)
        save_config("contestants.json", contestants)
    return RedirectResponse("/admin?tab=contestants", status_code=303)


@app.post("/admin/contestants/{contestant_id}/remove_tribe")
async def admin_remove_contestant_tribe(request: Request, contestant_id: str):
    form = await request.form()
    index = int(form.get("index", -1))
    contestants = load_config("contestants.json")
    for c in contestants:
        if c["id"] == contestant_id:
            tribes_list = c.get("tribes", [])
            if 0 <= index < len(tribes_list):
                tribes_list.pop(index)
    save_config("contestants.json", contestants)
    return RedirectResponse("/admin?tab=contestants", status_code=303)


@app.post("/admin/players/add")
async def admin_add_player(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    if name:
        players = get_players()
        if name not in players:
            players.append(name)
            save_config("players.json", players)
    return RedirectResponse("/admin?tab=players", status_code=303)


@app.post("/admin/players/remove")
async def admin_remove_player(request: Request):
    form = await request.form()
    name = form.get("name")
    players = [p for p in get_players() if p != name]
    save_config("players.json", players)
    return RedirectResponse("/admin?tab=players", status_code=303)


@app.post("/admin/settings/toggle_jury_override")
async def admin_toggle_jury_override(request: Request):
    settings = get_settings()
    settings["jury_override"] = not settings.get("jury_override", False)
    save_config("settings.json", settings)
    return RedirectResponse("/admin?tab=history", status_code=303)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
