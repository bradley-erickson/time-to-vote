import hashlib
import json
import time
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def _data_file(round_id: str) -> Path:
    return DATA_DIR / f"{round_id}.json"


def load_submissions(round_id: str) -> dict:
    f = _data_file(round_id)
    if not f.exists():
        return {}
    return json.loads(f.read_text())


def _record_hash(player: str, round_id: str, answers: dict, locked_at: str) -> str:
    payload = json.dumps(
        {"player": player, "round": round_id, "answers": answers, "locked_at": locked_at},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def save_submission(round_id: str, player: str, answers: dict) -> dict:
    """Locks in a player's answers for every question in a round at once.
    Overwrites any prior submission for that player/round, since the caller
    (main.py) only calls this once a player has no existing submission."""
    submissions = load_submissions(round_id)
    locked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    record = {
        "answers": answers,
        "locked_at": locked_at,
        "hash": _record_hash(player, round_id, answers, locked_at),
    }
    submissions[player] = record
    _data_file(round_id).write_text(json.dumps(submissions, indent=2))
    return record


def verify_submission(round_id: str, player: str, record: dict) -> bool:
    expected = _record_hash(player, round_id, record["answers"], record["locked_at"])
    return expected == record.get("hash")
