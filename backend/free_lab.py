from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import math
import re
import secrets
import sqlite3
import sys
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))

from engine import InputError, canonical_hash, canonical_json
from engine.ledger import anchor, append, verify
from engine.panel import commit, reveal
from engine.par import validate_par

from backend.eval.failure_modes import (
    drift_gate,
    executability_proxy,
    hallucination_gate,
    marginalization_probe,
    sim_real_gap,
)
from backend.eval.hunt_backends import FixtureBackend
from backend.eval.policy_fixtures import playback_rollout, reference_actions
from backend.eval.score_trace import score_trace
from backend.tools.presets import base_context, load, resolve


class LabError(InputError):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


MAX_POINTS = 512
MAX_BYTES = 256 * 1024
SHARE_DAYS = 7
_FRAME = re.compile(r"[A-Za-z0-9_.-]{1,80}")


@lru_cache(maxsize=1)
def samples() -> dict:
    constants, _ = load()
    context = base_context(constants)
    intended = context["T6A"]
    variants = {
        "clean": ("Nominal reach", context["T6B"]),
        "drifty": ("Drifting reach", context["T6DRIFT"]),
        "playback": ("Stalled playback", [[0, 0] for _ in intended]),
        "spike": ("Sensor spike", [[point[0], 1.4 if index == len(intended) - 1 else 0.02] for index, point in enumerate(intended)]),
    }
    return {name: {"name": title, "units": "m", "frame_id": "world", "intended": intended, "observed": observed} for name, (title, observed) in variants.items()}


def _finite(value: Any, name: str, lower: float, upper: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lower <= value <= upper:
        raise LabError(f"{name}: finite number in [{lower}, {upper}] required")
    return float(value)


def checked_pair(value: Any) -> dict:
    if not isinstance(value, dict) or value.get("units") != "m":
        raise LabError('units: explicitly declare "m" and convert both traces to metres')
    frame = value.get("frame_id")
    if not isinstance(frame, str) or _FRAME.fullmatch(frame) is None:
        raise LabError("frame_id: one declared shared frame is required")
    intended, observed = value.get("intended"), value.get("observed")
    if not isinstance(intended, list) or not 2 <= len(intended) <= MAX_POINTS:
        raise LabError("intended: 2..512 samples required")
    if not isinstance(observed, list) or len(observed) != len(intended):
        raise LabError("Both traces need the same number of points; no silent alignment")
    dimension = None
    for name, trace in (("intended", intended), ("observed", observed)):
        for index, point in enumerate(trace):
            if not isinstance(point, list) or len(point) not in (2, 3):
                raise LabError(f"{name}[{index}]: 2 or 3 coordinates required")
            if dimension is None:
                dimension = len(point)
            if len(point) != dimension:
                raise LabError("Both traces need one matching coordinate dimension")
            for coordinate in point:
                _finite(coordinate, f"{name}[{index}]", -1e6, 1e6)
    return {"units": "m", "frame_id": frame, "intended": intended, "observed": observed}


class LabService:
    key_quota = 200
    store_cap = 10000

    def __init__(self, root: Path | str, *, secret: str, clock: Callable[[], datetime] | None = None):
        if len(secret) < 32:
            raise ValueError("Lab secret requires at least 32 characters")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "free-lab.sqlite3"
        self.secret = secret.encode()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        with self._db() as database:
            database.executescript("""
                CREATE TABLE IF NOT EXISTS demo_keys (digest TEXT PRIMARY KEY, created TEXT NOT NULL, expires TEXT NOT NULL, day TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS shares (id TEXT PRIMARY KEY, owner TEXT NOT NULL, input_hash TEXT NOT NULL, created TEXT NOT NULL, expires TEXT NOT NULL, public_board INTEGER NOT NULL, artifact TEXT NOT NULL, consent TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS unique_board_input ON shares(input_hash) WHERE public_board=1;
                CREATE TABLE IF NOT EXISTS contributions (input_hash TEXT PRIMARY KEY, pair TEXT NOT NULL, consent TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS challenges (week TEXT PRIMARY KEY, commitment TEXT NOT NULL, seed TEXT NOT NULL, closes TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (week TEXT NOT NULL, owner TEXT NOT NULL, count INTEGER NOT NULL, best REAL, last_result TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(week,owner));
                CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, entry TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS quotas (identity TEXT NOT NULL, window INTEGER NOT NULL, count INTEGER NOT NULL, PRIMARY KEY(identity,window));
            """)

    @contextmanager
    def _db(self, write: bool = False):
        with closing(sqlite3.connect(self.database, timeout=10)) as database:
            database.row_factory = sqlite3.Row
            database.execute("PRAGMA foreign_keys=ON")
            with database:
                if write:
                    database.execute("BEGIN IMMEDIATE")
                yield database

    def _digest(self, value: str) -> str:
        return hmac.new(self.secret, value.encode(), hashlib.sha256).hexdigest()

    def _timestamp(self) -> str:
        return self.clock().astimezone(timezone.utc).isoformat()

    def _capacity(self, database, table: str):
        if table not in {"demo_keys", "shares", "contributions", "events"}:
            raise ValueError("Unknown bounded store")
        if database.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] >= self.store_cap:
            raise LabError("Demo store capacity reached. Export existing evidence and contact the operator.", 503)

    def _event(self, database, kind: str, payload: dict):
        self._capacity(database, "events")
        entries = [json.loads(row[0]) for row in database.execute("SELECT entry FROM events ORDER BY seq")]
        if not verify(entries)["ok"]:
            raise LabError("Lab ledger failed integrity verification; writes are blocked", 503)
        entry = append(entries, kind, payload, self._timestamp())
        database.execute("INSERT INTO events(seq,entry) VALUES (?,?)", (entry["index"], canonical_json(entry)))

    def throttle(self, identity: str, category: str, *, limit: int = 60, seconds: int = 60):
        window = (int(self.clock().timestamp()) // seconds) * seconds
        digest = self._digest(f"rate:{category}:{identity}")
        with self._db(True) as database:
            database.execute("DELETE FROM quotas WHERE window < ?", (int(self.clock().timestamp()) - 2 * 86400,))
            current = database.execute("SELECT count FROM quotas WHERE identity=? AND window=?", (digest, window)).fetchone()
            if current and current[0] >= limit:
                raise LabError("Free Lab rate limit reached. Retry after the current window.", 429)
            if database.execute("SELECT COUNT(*) FROM quotas").fetchone()[0] > 12000:
                raise LabError("Demo traffic capacity reached. Retry later.", 503)
            database.execute("INSERT INTO quotas VALUES (?,?,1) ON CONFLICT(identity,window) DO UPDATE SET count=count+1", (digest, window))

    def counts(self):
        with self._db() as database:
            return {name: database.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in ("shares", "contributions", "events", "demo_keys")}

    def issue_key(self):
        token = "gv_demo_" + secrets.token_urlsafe(32)
        now = self.clock()
        expiry = (now + timedelta(days=SHARE_DAYS)).isoformat()
        with self._db(True) as database:
            self._capacity(database, "demo_keys")
            database.execute("INSERT INTO demo_keys VALUES (?,?,?,?,0)", (self._digest(token), now.isoformat(), expiry, now.date().isoformat()))
        return {"key": token, "used": 0, "daily_quota": self.key_quota, "expires": expiry, "identity": "ANONYMOUS_DEMO_KEY", "email_delivery": "NOT_CONFIGURED"}

    def consume_key(self, token: Any, *, consume: bool = True):
        if not isinstance(token, str) or not token.startswith("gv_demo_") or len(token) > 100:
            raise LabError("A valid anonymous demo key is required", 401)
        digest = self._digest(token)
        now = self.clock()
        with self._db(True) as database:
            row = database.execute("SELECT * FROM demo_keys WHERE digest=?", (digest,)).fetchone()
            if row is None or datetime.fromisoformat(row["expires"]) <= now:
                raise LabError("Demo key expired or unrecognized", 401)
            used = row["used"] if row["day"] == now.date().isoformat() else 0
            if consume and used >= self.key_quota:
                raise LabError("Demo key daily quota reached", 429)
            if consume:
                used += 1
            database.execute("UPDATE demo_keys SET used=?,day=? WHERE digest=?", (used, now.date().isoformat(), digest))
            return {"owner": digest, "used": used, "daily_quota": self.key_quota, "expires": row["expires"]}

    def _input(self, body: dict):
        if not isinstance(body, dict):
            raise LabError("JSON object required")
        if "sample_id" in body:
            sample = body["sample_id"]
            if not isinstance(sample, str) or sample not in samples():
                raise LabError("Unknown synthetic sample")
            return checked_pair(samples()[sample]), "SYNTHETIC", samples()[sample]["name"]
        return checked_pair(body.get("pair")), "USER-SUPPLIED", "Uploaded trace"

    def _score_pair(self, pair: dict, label: str, name: str):
        card = score_trace(pair["intended"], pair["observed"], profile="draft-0", seed=7, evidence_prefix="free-lab", threshold=0.5)
        return {"scorecard": card, "label": label, "name": name, "input_hash": canonical_hash(pair), "scope": {"units": pair["units"], "frame_id": pair["frame_id"], "samples": len(pair["intended"]), "dimension": len(pair["intended"][0])}, "retention": {"trace_retained": False, "public": False}, "qualification": "DRAFT thresholds. Screening only; human review required."}

    def score(self, body: dict):
        if body.get("api_key"):
            self.consume_key(body["api_key"])
        return self._score_pair(*self._input(body))

    def parse_csv(self, source: Any):
        if not isinstance(source, str) or len(source.encode("utf-8")) > MAX_BYTES:
            raise LabError("CSV must be UTF-8 text within 256 KB")
        reader = csv.DictReader(io.StringIO(source.lstrip("\ufeff")))
        expected = ["ref_x", "ref_y", "obs_x", "obs_y", "units", "frame_id"]
        if reader.fieldnames != expected:
            raise LabError("CSV columns must be ref_x,ref_y,obs_x,obs_y,units,frame_id in that order")
        intended, observed = [], []
        scope = None
        for index, row in enumerate(reader):
            if index >= MAX_POINTS:
                raise LabError("CSV exceeds 512 samples")
            if None in row or any(value is None for value in row.values()):
                raise LabError(f"CSV row {index + 2}: wrong column count")
            row_scope = (row["units"], row["frame_id"])
            if scope is None:
                scope = row_scope
            if row_scope != scope:
                raise LabError("CSV scope changes between rows; comparison refused")
            try:
                intended.append([float(row["ref_x"]), float(row["ref_y"])])
                observed.append([float(row["obs_x"]), float(row["obs_y"])])
            except (TypeError, ValueError):
                raise LabError(f"CSV row {index + 2}: numeric coordinates required") from None
        pair = {"intended": intended, "observed": observed, "units": scope[0] if scope else None, "frame_id": scope[1] if scope else None}
        return {"pair": checked_pair(pair), "retained": False}

    def share(self, body: dict):
        if body.get("consent_share") is not True:
            raise LabError("Explicit public sharing consent is required")
        benchmark = body.get("consent_benchmark") is True
        if benchmark and body.get("contributor_terms") != "v1":
            raise LabError("Benchmark retention requires contributor terms v1")
        owner = self.consume_key(body.get("api_key"))["owner"]
        pair, label, name = self._input(body)
        artifact = self._score_pair(pair, label, name)
        return self._save_share(artifact, body, owner, pair if benchmark else None)

    def _save_share(self, artifact: dict, body: dict, owner: str, pair: dict | None = None):
        now = self.clock()
        identifier = secrets.token_hex(16)
        public_board = body.get("consent_board") is True
        receipt = {"schema": "consent-receipt/1", "public_result": True, "public_board": public_board, "trace_retained": pair is not None, "terms_version": "v1" if pair is not None else None, "timestamp": now.isoformat(), "input_hash": artifact["input_hash"], "expires": (now + timedelta(days=SHARE_DAYS)).isoformat()}
        artifact["retention"] = {"trace_retained": pair is not None, "public": True}
        try:
            with self._db(True) as database:
                self._capacity(database, "shares")
                if pair is not None:
                    self._capacity(database, "contributions")
                    database.execute("INSERT OR IGNORE INTO contributions VALUES (?,?,?)", (artifact["input_hash"], canonical_json(pair), canonical_json(receipt)))
                database.execute("INSERT INTO shares VALUES (?,?,?,?,?,?,?,?)", (identifier, owner, artifact["input_hash"], now.isoformat(), receipt["expires"], int(public_board), canonical_json(artifact), canonical_json(receipt)))
                self._event(database, "lab.share", {"id": identifier, "artifact_hash": canonical_hash(artifact), "consent_hash": canonical_hash(receipt)})
        except sqlite3.IntegrityError:
            raise LabError("This input fingerprint already has a public board entry. Duplicate ranking is refused.", 409) from None
        return {"id": identifier, "consent_receipt": receipt, "artifact_hash": canonical_hash(artifact)}

    def get_share(self, identifier: str):
        if not isinstance(identifier, str) or re.fullmatch(r"[a-f0-9]{32}", identifier) is None:
            raise LabError("Unknown or expired share", 404)
        with self._db() as database:
            row = database.execute("SELECT artifact,consent,expires FROM shares WHERE id=?", (identifier,)).fetchone()
        if row is None or datetime.fromisoformat(row["expires"]) <= self.clock():
            raise LabError("Unknown or expired share", 404)
        return {"id": identifier, "artifact": json.loads(row["artifact"]), "consent_receipt": json.loads(row["consent"]), "expires": row["expires"]}

    @staticmethod
    @lru_cache(maxsize=1)
    def _seed_board():
        rows = []
        for index in range(10):
            intended = [[step * 0.1, 0.0] for step in range(24)]
            observed = [[point[0], (index + 1) * 0.012 * step / 23] for step, point in enumerate(intended)]
            card = score_trace(intended, observed, seed=index, profile="draft-0")
            gap = next(gate["measurement"] for gate in card["payload"]["gates"] if gate["gate"] == "frechet_gap")
            rows.append({"id": f"synthetic-example-{index + 1}", "name": f"Example reach {index + 1:02}", "task": "reach", "frame_id": "world", "label": "SYNTHETIC", "gap": gap, "share_id": None, "scope": "24-point task-space example, not a real-robot ranking"})
        return rows

    def board(self):
        with self._db() as database:
            stored = database.execute("SELECT id,artifact FROM shares WHERE public_board=1 AND expires>? ORDER BY created DESC LIMIT 100", (self._timestamp(),)).fetchall()
        rows = [dict(row) for row in self._seed_board()]
        for entry in stored:
            artifact = json.loads(entry["artifact"])
            if artifact.get("kind") == "duel":
                continue
            gap = next(gate["measurement"] for gate in artifact["scorecard"]["payload"]["gates"] if gate["gate"] == "frechet_gap")
            rows.append({"id": entry["id"], "name": "Anonymous contribution", "task": "declared trace", "frame_id": artifact["scope"]["frame_id"], "label": artifact["label"], "gap": gap, "share_id": entry["id"], "scope": artifact["scope"]})
        rows.sort(key=lambda row: (row["label"], row["frame_id"], row["gap"]))
        return {"entries": rows, "qualification": "Grouped by source and frame; not a cross-task hardware leaderboard. Ten engine-computed synthetic examples; no OXE provenance claimed."}

    def _week(self):
        now = self.clock().astimezone(timezone.utc)
        monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return monday.date().isoformat(), monday + timedelta(days=7)

    def _challenge(self):
        week, closes = self._week()
        with self._db(True) as database:
            row = database.execute("SELECT * FROM challenges WHERE week=?", (week,)).fetchone()
            if row is None:
                seed = secrets.token_hex(32)
                commitment = commit(seed, 50)["commitment"]
                self._event(database, "challenge.commit", {"week": week, "commitment": commitment, "case_count": 50})
                database.execute("INSERT INTO challenges VALUES (?,?,?,?)", (week, commitment, seed, closes.isoformat()))
                row = database.execute("SELECT * FROM challenges WHERE week=?", (week,)).fetchone()
            return dict(row)

    def challenge(self):
        current = self._challenge()
        with self._db() as database:
            winners = database.execute("SELECT owner,count,best FROM attempts WHERE week=? AND published=1 ORDER BY best ASC,count ASC LIMIT 25", (current["week"],)).fetchall()
        return {"week": current["week"], "commitment": current["commitment"], "case_count": 50, "closes": current["closes"], "label": "SYNTHETIC", "identity_limit": "Anonymous keys are not verified people; issuance limits reduce, but do not eliminate, multi-key gaming.", "winners": [{"entry": row["owner"][:10], "attempts": row["count"], "disturbance": row["best"]} for row in winners]}

    def trial(self, body: dict):
        owner = self.consume_key(body.get("api_key"))["owner"]
        bias = _finite(body.get("bias"), "bias", 0, 1.5)
        noise = _finite(body.get("noise_scale"), "noise_scale", 0, 2)
        current = self._challenge()
        seed = int(current["seed"][:12], 16)
        with self._db(True) as database:
            saved = database.execute("SELECT * FROM attempts WHERE week=? AND owner=?", (current["week"], owner)).fetchone()
            count = saved["count"] if saved else 0
            if count >= 50:
                raise LabError("Weekly attempt cap reached: 50 per demo key", 429)
            result = FixtureBackend("clean", horizon=48, seed=seed).evaluate({"bias": bias, "noise_scale": noise})
            disturbance = bias + noise * 0.1
            best = saved["best"] if saved else None
            if result["breaks"] and (best is None or disturbance < best):
                best = disturbance
            payload = {"week": current["week"], "attempts": count + 1, "remaining": 49 - count, "breaks": result["breaks"], "measurement": result["measurement"], "bias": bias, "noise_scale": noise, "commitment": current["commitment"], "label": "SYNTHETIC", "best_disturbance": best}
            database.execute("INSERT INTO attempts VALUES (?,?,?,?,?,0) ON CONFLICT(week,owner) DO UPDATE SET count=excluded.count,best=excluded.best,last_result=excluded.last_result", (current["week"], owner, count + 1, best, canonical_json(payload)))
            self._event(database, "challenge.trial", {"week": current["week"], "entry": owner[:10], "receipt_hash": canonical_hash(payload)})
        return payload

    def publish_challenge(self, body: dict):
        if body.get("consent_public") is not True:
            raise LabError("Explicit public consent required")
        owner = self.consume_key(body.get("api_key"))["owner"]
        week, _ = self._week()
        with self._db(True) as database:
            row = database.execute("SELECT best FROM attempts WHERE week=? AND owner=?", (week, owner)).fetchone()
            if row is None or row["best"] is None:
                raise LabError("Find a breaking trial before publishing a challenge result")
            database.execute("UPDATE attempts SET published=1 WHERE week=? AND owner=?", (week, owner))
            self._event(database, "challenge.publish", {"week": week, "entry": owner[:10], "consent_public": True})
        return {"published": True, "week": week, "entry": owner[:10]}

    def reveal(self, week: str):
        if not isinstance(week, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", week) is None:
            raise LabError("A recorded week identifier is required")
        with self._db() as database:
            row = database.execute("SELECT * FROM challenges WHERE week=?", (week,)).fetchone()
        if row is None:
            raise LabError("Unknown challenge week", 404)
        if self.clock() < datetime.fromisoformat(row["closes"]):
            raise LabError("Seed reveal refused while this challenge week is open", 409)
        checked = reveal(row["commitment"], row["seed"], 50)
        return {**checked, "week": week, "seed": row["seed"], "fixture_seed": int(row["seed"][:12], 16), "commitment": row["commitment"], "method": "FixtureBackend('clean', horizon=48, seed=fixture_seed); evaluate submitted bias/noise_scale"}

    def failure_demo(self, body: dict):
        mode = body.get("mode")
        if mode not in ("fm1", "fm2", "fm3", "fm4", "fm5"):
            raise LabError("Unknown failure mode")
        if mode in ("fm3", "fm4") and "pair" in body:
            raise LabError("Custom encode/decode or policy callables are library-only; trace uploads cannot supply them")
        pair, label, _ = self._input(body if "pair" in body or "sample_id" in body else {"sample_id": "drifty"})
        if mode == "fm1":
            measurement = drift_gate(pair["intended"], pair["observed"], threshold=0.5)
        elif mode == "fm2":
            measurement = executability_proxy(pair["observed"])
        elif mode == "fm3":
            measurement = hallucination_gate(lambda point: [0.0] * len(point), lambda point: point, pair["observed"], threshold=0.25)
        elif mode == "fm4":
            measurement = marginalization_probe(playback_rollout, reference_actions(24), probe_offsets=[0.5, -0.3], seed=7)
        else:
            measurement = sim_real_gap(pair["intended"], pair["observed"])
        return {"mode": mode, "label": "SYNTHETIC" if mode in ("fm3", "fm4") else label, "measurement": measurement, "qualification": "Toy callable demonstration only" if mode in ("fm3", "fm4") else "PROXY task-space screening" if mode == "fm2" else "DRAFT scoped measurement", "independence": "Diagnostic only; no automatic policy changes"}

    def duel(self, body: dict):
        left = self._input(body.get("left", {}))
        right = self._input(body.get("right", {}))
        if left[0]["frame_id"] != right[0]["frame_id"] or len(left[0]["intended"]) != len(right[0]["intended"]) or len(left[0]["intended"][0]) != len(right[0]["intended"][0]):
            raise LabError("A duel requires the same frame, horizon and dimension on both sides")
        return {"kind": "duel", "left": self._score_pair(*left), "right": self._score_pair(*right), "input_hash": canonical_hash({"left": left[0], "right": right[0]}), "caption": "Two separately scored traces. Lower deviation is not a whole-system safety finding.", "retention": {"trace_retained": False, "public": False}}

    def share_duel(self, body: dict):
        if body.get("consent_share") is not True:
            raise LabError("Explicit public result sharing consent required")
        owner = self.consume_key(body.get("api_key"))["owner"]
        return self._save_share(self.duel(body), {"consent_share": True}, owner)

    def ledger(self):
        with self._db() as database:
            entries = [json.loads(row[0]) for row in database.execute("SELECT entry FROM events ORDER BY seq")]
        return {**verify(entries), "anchor": anchor(entries), "qualification": "TAMPER-EVIDENT relative to a retained external anchor. Internal links alone do not expose a full rewrite or truncation."}

    def example_par(self):
        constants, _ = load()
        envelope = resolve("$PAR", base_context(constants))
        return {"envelope": envelope, "verification": validate_par(envelope), "label": "SYNTHETIC", "signature": "UNSIGNED"}

    def extended_metrics(self, body: dict):
        from engine.fall_impact import assess_fall_impact
        from engine.success_time import summarize_times
        times = body.get("times", [2, 4, None, 7])
        if not isinstance(times, list) or not 1 <= len(times) <= 512:
            raise LabError("times: 1..512 first-success sample indexes or null required")
        return {"success_time": summarize_times(times), "fall_impact": assess_fall_impact(body.get("impact")), "label": "DRAFT", "time_unit": "sample index, not seconds", "qualification": "Task success is reported separately and cannot offset a blocked safety gate. Fall/impact is a placeholder, not an assessment."}


def create_lab_router(service: LabService):
    router = APIRouter(prefix="/api/lab/v1", tags=["Free Lab"])

    def run(request, operation, body=None, *, category="api"):
        identity = request.client.host if request.client else "unknown"
        try:
            service.throttle(identity, category, limit=5 if category == "keys" else 90, seconds=3600 if category == "keys" else 60)
            if body is not None:
                body = dict(body)
                authorization = request.headers.get("authorization", "")
                if authorization.startswith("Bearer "):
                    body["api_key"] = authorization[7:]
                return operation(body)
            return operation()
        except LabError as failure:
            raise HTTPException(failure.status, {"error": "input" if failure.status == 422 else "refused", "message": str(failure)}) from None
        except InputError as failure:
            raise HTTPException(422, {"error": "input", "message": str(failure)}) from None
        except Exception:
            error_id = secrets.token_hex(4)
            raise HTTPException(500, {"error": "internal", "error_id": error_id}) from None

    @router.post("/score")
    def score_route(request: Request, body: dict[str, Any]):
        return run(request, service.score, body)

    @router.post("/parse")
    def parse_route(request: Request, body: dict[str, Any]):
        return run(request, lambda value: service.parse_csv(value.get("csv")), body)

    @router.post("/keys")
    def keys_route(request: Request, body: dict[str, Any]):
        return run(request, service.issue_key, category="keys")

    @router.post("/usage")
    def usage_route(request: Request, body: dict[str, Any]):
        return run(request, lambda value: {key: item for key, item in service.consume_key(value.get("api_key"), consume=False).items() if key != "owner"}, body)

    @router.post("/share")
    def share_route(request: Request, body: dict[str, Any]):
        return run(request, service.share, body)

    @router.get("/shares/{identifier}")
    def get_share_route(request: Request, identifier: str):
        return run(request, lambda: service.get_share(identifier))

    @router.get("/board")
    def board_route(request: Request):
        return run(request, service.board)

    @router.get("/challenge")
    def challenge_route(request: Request):
        return run(request, service.challenge)

    @router.post("/challenge/trial")
    def trial_route(request: Request, body: dict[str, Any]):
        return run(request, service.trial, body)

    @router.post("/challenge/publish")
    def publish_route(request: Request, body: dict[str, Any]):
        return run(request, service.publish_challenge, body)

    @router.get("/challenge/reveal")
    def reveal_route(request: Request, week: str):
        return run(request, lambda: service.reveal(week))

    @router.post("/failure-demo")
    def failure_route(request: Request, body: dict[str, Any]):
        return run(request, service.failure_demo, body)

    @router.post("/duel")
    def duel_route(request: Request, body: dict[str, Any]):
        return run(request, service.duel, body)

    @router.post("/duel/share")
    def duel_share_route(request: Request, body: dict[str, Any]):
        return run(request, service.share_duel, body)

    @router.get("/ledger")
    def ledger_route(request: Request):
        return run(request, service.ledger)

    @router.post("/par")
    def par_route(request: Request, body: dict[str, Any]):
        return run(request, lambda value: service.example_par(), body)

    @router.post("/extended-metrics")
    def metrics_route(request: Request, body: dict[str, Any]):
        return run(request, service.extended_metrics, body)

    return router