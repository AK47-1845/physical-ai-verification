from __future__ import annotations

import hashlib
import json
import secrets
import time

from argon2 import PasswordHasher
from sqlalchemy import select

from backend.catalog import EMBODIMENTS, STANDARDS
from backend.config import ROOT
from backend.engine import compare_embodiments, default_profile, evaluate, fingerprint
from backend.evidence import make_bundle
from backend.fixtures import SCENARIOS, make_trace
from backend.formal import BoundQuery, verify_bounds
from backend.runtime import current_runtime, runtime_decision
from backend.schemas import Embodiment, GateProfile, Telemetry, Trace
from backend.store import AuditEvent, Record, Store, User, serialize

DEMO_TENANT = "ltts-sandbox"
PASSWORDS = PasswordHasher()


class Conflict(ValueError):
    pass


def run_summary(record: dict, review: dict | None = None) -> dict:
    data = record["data"]
    trace = data["trace"]
    result = data["result"]
    return {"id": record["id"], "name": trace["name"], "task": trace["task"], "policy_version": trace["policy_version"],
            "embodiment_id": trace["embodiment_id"], "evidence_kind": trace["evidence_kind"],
            "reference_kind": trace["reference_kind"], "created_at": record["created_at"], "created_by": record["created_by"],
            "verdict": result["verdict"], "coverage": result["coverage"], "content_hash": record["content_hash"],
            "profile_name": data["profile"]["name"], "profile_version": data["profile"]["version"],
            "review_state": review["decision"] if review else "unreviewed", "review_revision": review["revision"] if review else 0,
            "failed_gates": sum(gate["status"] == "BLOCK" for gate in result["gates"]),
            "mean_drift": next((gate["value"] for gate in result["gates"] if gate["metric"] == "mean_drift"), None),
            "release_eligible": False}


class Governance:
    def __init__(self, store: Store, secret: str):
        self.store = store
        self.secret = secret

    def seed_demo(self) -> None:
        self.store.ensure_tenant(DEMO_TENANT, "Physical AI validation workspace")
        if self.store.list(DEMO_TENANT, "profile", 1):
            return
        traces = [(scenario, make_trace(scenario)) for scenario in SCENARIOS]
        traces += [(f"nominal-{embodiment}", make_trace(embodiment=embodiment)) for embodiment in ("ur5e", "g1-task-space")]
        traces += [(f"nominal-{seed}", make_trace(seed=seed)) for seed in (11, 19, 31)]
        profile = default_profile()
        with self.store.transaction(DEMO_TENANT) as (session, tenant):
            if session.scalar(select(Record.id).where(Record.tenant_id == DEMO_TENANT, Record.kind == "profile")):
                return
            for role, name in [("engineer", "Alex Morgan"), ("reviewer", "Sam Rivera"), ("admin", "Workspace Admin"), ("viewer", "Read-only Observer")]:
                session.add(User(id=f"demo-{role}", tenant_id=tenant.id, email=f"{role}@sandbox.invalid", display_name=name,
                                 role=role, password_hash=PASSWORDS.hash(secrets.token_urlsafe(32))))
            for entry in EMBODIMENTS:
                data = {key: value for key, value in entry.items() if key != "id"}
                self.store.add_record(session, tenant, "embodiment", Embodiment.model_validate(data).model_dump(), "system:bootstrap", entry["id"])
            self.store.add_record(session, tenant, "profile", profile.model_dump(), "system:bootstrap", "profile-default")
            for scenario_id, trace in traces:
                dataset = self.store.add_record(session, tenant, "dataset", {"trace": trace.model_dump(), "scenario": scenario_id}, "system:bootstrap", f"dataset-{scenario_id}")
                self.store.add_record(session, tenant, "run", {"trace": trace.model_dump(), "profile": profile.model_dump(),
                    "result": evaluate(trace, profile), "dataset_id": dataset.id}, "demo-engineer")
            self._seed_recorded_sample(session, tenant)

    def _seed_recorded_sample(self, session, tenant) -> None:
        source = ROOT / "reference" / "original-mvp" / "dataset" / "scenarios" / "droid_pour_s1"
        if not (source / "pair.json").exists():
            source = ROOT / "backend" / "demo-data"
        if not (source / "pair.json").exists():
            return
        pair_bytes = (source / "pair.json").read_bytes()
        pair = json.loads(pair_bytes)
        card = json.loads((source / "card.json").read_text(encoding="utf-8"))
        if len(pair["sim"]) > 512:
            return
        embodiment = {"name": "DROID staged XY", "family": "manipulator", "degrees_of_freedom": 7,
            "coordinate_frame": "franka-staged-xy", "units": "m", "dimension": 2, "hardware_validated": False,
            "description": "Public capture staged by the original MVP; only commanded/observed XY are available."}
        self.store.add_record(session, tenant, "embodiment", embodiment, "system:bootstrap", "droid-xy")
        trace = Trace.model_validate({"name": "DROID pour / staged XY", "task": "pour", "embodiment_id": "droid-xy",
            "policy_version": "recorded-teleoperation", "evidence_kind": "recorded", "reference_kind": "commanded",
            "units": "m", "coordinate_frame": "franka-staged-xy", "reference": pair["sim"], "observed": pair["real"],
            "provenance": {"source": card["source"], "license": card["license"],
                "source_sha256": hashlib.sha256(pair_bytes).hexdigest(), "transforms": card["transforms"] + ["Only XY retained by original adapter; no timestamps invented", "SHA256 refers to supplied staged pair.json, not upstream HDF5"],
                "attribution": "DROID/AUTOLab; source declaration from original MVP, upstream bytes not re-downloaded"}})
        dataset = self.store.add_record(session, tenant, "dataset", {"trace": trace.model_dump(), "scenario": "recorded-droid"}, "system:bootstrap", "dataset-droid")
        profile = default_profile().model_dump()
        profile.update({"name": "DROID XY evidence review", "coordinate_frame": "franka-staged-xy", "dimension": 2, "workspace_lower": [-1.0, -1.0], "workspace_upper": [1.0, 1.0]})
        parsed_profile = GateProfile.model_validate(profile)
        self.store.add_record(session, tenant, "profile", profile, "system:bootstrap", "profile-droid")
        self.store.add_record(session, tenant, "run", {"trace": trace.model_dump(), "profile": profile,
            "result": evaluate(trace, parsed_profile), "dataset_id": dataset.id}, "demo-engineer")

    def workspace(self, actor: dict) -> dict:
        tenant = actor["tenant_id"]
        reviews = self.store.list(tenant, "review", 500)
        latest_reviews = {}
        for record in reviews:
            review = record["data"]
            current = latest_reviews.get(review["run_id"])
            if current is None or review["revision"] > current["revision"]:
                latest_reviews[review["run_id"]] = review
        runs = [run_summary(record, latest_reviews.get(record["id"])) for record in self.store.list(tenant, "run", 100)]
        datasets = []
        for record in self.store.list(tenant, "dataset", 100):
            trace = record["data"]["trace"]
            datasets.append({"id": record["id"], "name": trace["name"], "task": trace["task"], "embodiment_id": trace["embodiment_id"],
                "evidence_kind": trace["evidence_kind"], "reference_kind": trace["reference_kind"], "samples": len(trace["observed"]),
                "units": trace["units"], "coordinate_frame": trace["coordinate_frame"], "dimension": len(trace["observed"][0]),
                "timing_available": trace["timestamps_s"] is not None, "content_hash": record["content_hash"],
                "source": trace["provenance"]["source"], "license": trace["provenance"]["license"], "scenario": record["data"].get("scenario")})
        return {"runs": runs, "datasets": datasets, "scope": "Latest 100 evaluations and datasets",
                "profiles": [{"id": record["id"], **record["data"], "content_hash": record["content_hash"]} for record in self.store.list(tenant, "profile")],
                "embodiments": [{"id": record["id"], **record["data"]} for record in self.store.list(tenant, "embodiment")],
                "counts": {status: sum(run["verdict"] == status for run in runs) for status in ("PASS", "REVIEW", "BLOCK", "INSUFFICIENT")},
                "audit": self.store.audit(tenant, 8), "standards": STANDARDS,
                "scenarios": [{"id": key, "name": value[0], "description": value[1]} for key, value in SCENARIOS.items()]}

    def add_dataset(self, trace: Trace, actor: dict) -> dict:
        with self.store.transaction(actor["tenant_id"]) as (session, tenant):
            embodiment = self.store.find(session, tenant.id, trace.embodiment_id, "embodiment").data
            if (trace.coordinate_frame, trace.units, len(trace.observed[0])) != (embodiment["coordinate_frame"], embodiment["units"], embodiment["dimension"]):
                raise ValueError("Trace does not match its registered embodiment contract")
            return serialize(self.store.add_record(session, tenant, "dataset", {"trace": trace.model_dump(), "scenario": None}, actor["id"]))

    def evaluate_dataset(self, dataset_id: str, profile_id: str, actor: dict, idempotency_key: str | None = None) -> dict:
        trace = Trace.model_validate(self.store.get(actor["tenant_id"], dataset_id, "dataset")["data"]["trace"])
        profile = GateProfile.model_validate(self.store.get(actor["tenant_id"], profile_id, "profile")["data"])
        request_hash = fingerprint({"dataset": dataset_id, "profile": profile_id})
        memo_id = f"idem_{fingerprint([actor['id'], idempotency_key])[:40]}" if idempotency_key else None
        result = evaluate(trace, profile)
        with self.store.transaction(actor["tenant_id"]) as (session, tenant):
            if memo_id:
                existing = session.scalar(select(Record).where(Record.tenant_id == tenant.id, Record.id == memo_id, Record.kind == "idempotency"))
                if existing:
                    if existing.data["request_hash"] != request_hash:
                        raise Conflict("Idempotency key was already used for another request")
                    return serialize(self.store.find(session, tenant.id, existing.data["run_id"], "run"))
            record = self.store.add_record(session, tenant, "run", {"trace": trace.model_dump(), "profile": profile.model_dump(), "result": result, "dataset_id": dataset_id}, actor["id"])
            if memo_id:
                self.store.add_record(session, tenant, "idempotency", {"request_hash": request_hash, "run_id": record.id}, actor["id"], memo_id)
            return serialize(record)

    def experiment(self, scenario: str, profile_id: str, budget: int, maximum: float, seed: int, actor: dict) -> dict:
        profile = GateProfile.model_validate(self.store.get(actor["tenant_id"], profile_id, "profile")["data"])
        prepared = []
        for index in range(budget):
            severity = maximum * index / (budget - 1)
            trace = make_trace(scenario, seed=seed, severity=severity)
            prepared.append((severity, trace, evaluate(trace, profile)))
        with self.store.transaction(actor["tenant_id"]) as (session, tenant):
            rows = []
            for severity, trace, result in prepared:
                run = self.store.add_record(session, tenant, "run", {"trace": trace.model_dump(), "profile": profile.model_dump(), "result": result, "dataset_id": None}, actor["id"])
                rows.append({"run_id": run.id, "severity": severity, "verdict": result["verdict"],
                             "mean_drift": next(gate["value"] for gate in result["gates"] if gate["metric"] == "mean_drift")})
            return serialize(self.store.add_record(session, tenant, "experiment", {"scenario": scenario, "seed": seed,
                "profile_id": profile_id, "budget": budget, "maximum": maximum, "results": rows,
                "method": "Deterministic synthetic disturbance sweep, not physics simulation or hardware testing"}, actor["id"]))

    def review(self, run_id: str, decision: str, note: str, expected_revision: int, actor: dict) -> dict:
        with self.store.transaction(actor["tenant_id"]) as (session, tenant):
            run = self.store.find(session, tenant.id, run_id, "run", lock=True)
            history = list(session.scalars(select(Record).where(Record.tenant_id == tenant.id, Record.kind == "review")))
            revision = max((entry.data["revision"] for entry in history if entry.data["run_id"] == run_id), default=0)
            if expected_revision != revision:
                raise Conflict("Review changed. Refresh before submitting a decision")
            if decision != "request_review" and actor["id"] == run.created_by:
                raise Conflict("Independent review required; the run creator cannot approve their own evidence")
            if decision == "accept_evidence" and run.data["result"]["verdict"] in ("BLOCK", "INSUFFICIENT"):
                raise Conflict("Blocked or incomplete evidence cannot be accepted")
            return serialize(self.store.add_record(session, tenant, "review", {"run_id": run_id, "decision": decision,
                "note": note, "revision": revision + 1, "reviewer": actor["id"], "release_eligible": False}, actor["id"]))

    def transfer(self, baseline_id: str, candidate_id: str, actor: dict) -> dict:
        baseline = self.store.get(actor["tenant_id"], baseline_id, "dataset")["data"]["trace"]
        candidate = self.store.get(actor["tenant_id"], candidate_id, "dataset")["data"]["trace"]
        result = compare_embodiments(Trace.model_validate(baseline), Trace.model_validate(candidate))
        with self.store.transaction(actor["tenant_id"]) as (session, tenant):
            return serialize(self.store.add_record(session, tenant, "transfer", {"baseline_id": baseline_id,
                "candidate_id": candidate_id, "result": result}, actor["id"]))

    def formal(self, query: BoundQuery, actor: dict) -> dict:
        result = verify_bounds(query)
        with self.store.transaction(actor["tenant_id"]) as (session, tenant):
            return serialize(self.store.add_record(session, tenant, "proof", {"query": query.model_dump(), "result": result}, actor["id"]))

    def start_runtime(self, name: str, profile_id: str, embodiment_id: str, actor: dict) -> dict:
        with self.store.transaction(actor["tenant_id"]) as (session, tenant):
            profile = self.store.find(session, tenant.id, profile_id, "profile").data
            embodiment = self.store.find(session, tenant.id, embodiment_id, "embodiment").data
            if (profile["units"], profile["dimension"], profile["coordinate_frame"]) != ("m", 3, embodiment["coordinate_frame"]):
                raise ValueError("Runtime requires a compatible 3D meter embodiment and profile")
            return serialize(self.store.add_record(session, tenant, "runtime", {"name": name, "profile": profile,
                "embodiment_id": embodiment_id, "state": {"decision": "HOLD", "latched": False, "last_sequence": None,
                    "reasons": ["Awaiting first telemetry"], "expires_at_ms": 0.0}}, actor["id"]))

    def telemetry(self, runtime_id: str, sample: Telemetry, actor: dict) -> dict:
        with self.store.transaction(actor["tenant_id"]) as (session, tenant):
            record = self.store.find(session, tenant.id, runtime_id, "runtime", lock=True)
            previous = record.data["state"]
            state = runtime_decision(sample, previous, GateProfile.model_validate(record.data["profile"]), time.time() * 1000)
            record.data = {**record.data, "state": state}
            record.content_hash = fingerprint(record.data)
            if state["decision"] != previous["decision"] or (state["latched"] and not previous.get("latched")):
                self.store.append_audit(session, tenant, actor["id"], f"runtime.{state['decision'].lower()}", record.id, record.content_hash, {"reasons": state["reasons"], "sequence": sample.sequence})
            return {"id": record.id, **state}

    def reset_runtime(self, runtime_id: str, note: str, actor: dict) -> dict:
        with self.store.transaction(actor["tenant_id"]) as (session, tenant):
            record = self.store.find(session, tenant.id, runtime_id, "runtime", lock=True)
            state = record.data["state"]
            if not state.get("sample"):
                raise Conflict("Fresh safe telemetry is required before resetting")
            if actor["id"] == record.created_by:
                raise Conflict("Independent reset authority required")
            sample = Telemetry.model_validate(state["sample"])
            checked = runtime_decision(sample, {"last_sequence": sample.sequence - 1}, GateProfile.model_validate(record.data["profile"]), time.time() * 1000)
            if checked["decision"] != "ALLOW":
                raise Conflict("Unsafe or stale telemetry prevents reset")
            record.data = {**record.data, "state": {**state, "latched": False, "decision": "HOLD", "reasons": ["Reset authorized; awaiting next telemetry"], "expires_at_ms": 0.0}}
            record.content_hash = fingerprint(record.data)
            self.store.append_audit(session, tenant, actor["id"], "runtime.reset", record.id, record.content_hash, {"note": note})
            return serialize(record)

    def get_runtime(self, runtime_id: str, actor: dict) -> dict:
        record = self.store.get(actor["tenant_id"], runtime_id, "runtime")
        return {**record, "data": {**record["data"], "state": current_runtime(record["data"]["state"], time.time() * 1000)}}

    def export(self, run_id: str, actor: dict) -> tuple[bytes, dict]:
        with self.store.transaction(actor["tenant_id"]) as (session, tenant):
            if tenant.sequence > 10_000:
                raise Conflict("Audit export limit reached; use an externally checkpointed archive workflow")
            run = serialize(self.store.find(session, tenant.id, run_id, "run"))
            self.store.append_audit(session, tenant, actor["id"], "evidence.exported", run_id, run["content_hash"])
            session.flush()
            entries = list(session.scalars(select(AuditEvent).where(AuditEvent.tenant_id == tenant.id).order_by(AuditEvent.sequence)))
            audit = [{**entry.payload, "event_hash": entry.event_hash} for entry in entries]
            reviews = [serialize(entry) for entry in session.scalars(select(Record).where(Record.tenant_id == tenant.id, Record.kind == "review")) if entry.data["run_id"] == run_id]
            return make_bundle(run, audit, reviews, self.secret)