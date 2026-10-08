"""External eval ingestion: ONE protocol, honest statuses (FR-42).

parse() returns {"records": [...], "summary": {...}, "provenance": {...}}
for every adapter that parses. Statuses (see D-night-11):
  STUB     - schema unknown; parse() refuses loudly instead of guessing.
  DERIVED  - shape documented from the harness's own primary sources
             (code/README/docs, URL + date pinned); strict validation;
             transcription cross-checks where the native artifact has
             redundant fields. NOT a real-log run yet.
  VERIFIED:<date>:<harness-version> - graduated with a recorded
             real-shape run: fixture + test + date (GRADUATION.md).
Halos outputs get an ingestion point now; we absorb NVIDIA evidence,
never fight on sim.
"""

import json

from engine import InputError


class AdapterError(InputError):
    """Refusals + conformance failures. Loud by design."""


class ExternalEval:
    """Protocol base: name + SCHEMA_STATUS + parse(). Subclass per harness."""

    name = "base"
    SCHEMA_STATUS = "STUB"
    SOURCE = None
    SOURCE_URLS = ()
    DERIVED_DATE = None
    STUB_REASON = "schema unknown"

    def parse(self, log) -> dict:
        """Parse a harness log to records + summary + provenance."""
        raise AdapterError(
            f"{self.name}: schema UNVERIFIED against the real harness; "
            f"refusing to guess. Graduate with a recorded real-log run.")


def _need_str(doc, key, where):
    val = doc.get(key)
    if not val or not isinstance(val, str):
        raise AdapterError(f"{where}.{key}: non-empty string required")
    return val


def _need_int(doc, key, where, *, lo=None, hi=None):
    val = doc.get(key)
    if isinstance(val, bool) or not isinstance(val, int):
        raise AdapterError(f"{where}.{key}: int required, got {val!r}")
    if lo is not None and val < lo:
        raise AdapterError(f"{where}.{key}: must be >= {lo}, got {val}")
    if hi is not None and val > hi:
        raise AdapterError(f"{where}.{key}: must be <= {hi}, got {val}")
    return val


def _need_num(doc, key, where):
    val = doc.get(key)
    if (isinstance(val, bool) or not isinstance(val, (int, float))
            or val != val or val in (float("inf"), float("-inf"))):
        raise AdapterError(f"{where}.{key}: finite number required, "
                           f"got {val!r}")
    return val


def _need_bool(doc, key, where):
    val = doc.get(key)
    if not isinstance(val, bool):
        raise AdapterError(f"{where}.{key}: strict bool required, "
                           f"got {val!r}")
    return val


def _opt_int(doc, key, where, *, lo=None):
    if doc.get(key) is None:
        return None
    return _need_int(doc, key, where, lo=lo)


def _wilson_95(n_success: int, n_trials: int) -> tuple:
    """95% Wilson score interval in PERCENT, transcribed from
    lerobot/utils/eval_stats.py::wilson_interval (lerobot@8c920c42).
    Used only to cross-check a reported pc_success_ci95; drift in the
    harness formula must fail loud here, never pass silent."""
    import math
    from statistics import NormalDist
    z = NormalDist().inv_cdf(0.975)
    p = n_success / n_trials
    z2 = z * z
    den = 1.0 + z2 / n_trials
    centre = (p + z2 / (2.0 * n_trials)) / den
    half = z * math.sqrt(p * (1.0 - p) / n_trials
                         + z2 / (4.0 * n_trials * n_trials)) / den
    return (100.0 * max(0.0, centre - half),
            100.0 * min(1.0, centre + half))


class DerivedEval(ExternalEval):
    """Base for DERIVED adapters: strict parse + labeled provenance."""

    SCHEMA_STATUS = "DERIVED"

    def parse(self, log) -> dict:
        if isinstance(log, str):
            doc = loads_json(log)
        elif isinstance(log, dict):
            doc = log
        else:
            raise AdapterError(f"{self.name}: log must be JSON text or "
                               f"a dict, got {type(log).__name__}")
        return self._wrap(self._parse_doc(doc))

    def _parse_doc(self, doc: dict) -> dict:
        raise NotImplementedError

    STATUS_NOTE = ("DERIVED: shape documented from the "
                   "harness's own primaries, not yet a "
                   "recorded real-log run (D-night-11).")

    def _extra_provenance(self, parsed: dict) -> dict:
        return {}

    def _wrap(self, parsed: dict) -> dict:
        return {"records": parsed["records"], "summary": parsed["summary"],
                "provenance": {
                    "harness": self.name,
                    "schema_status": self.SCHEMA_STATUS,
                    "source": self.SOURCE, "source_urls": list(
                        self.SOURCE_URLS),
                    "derived_date": self.DERIVED_DATE,
                    "note": self.STATUS_NOTE,
                    **self._extra_provenance(parsed)}}


class SimplerLiberoEval(DerivedEval):
    """SIMPLER per-episode records + LIBERO eval_stats transcriptions.

    LIBERO native (VERIFIED from libero/lifelong/evaluate.py): the
    script torch.saves {"loss", "success_rate"} per benchmark/task/seed
    checkpoint and prints the pair. We ingest a JSON transcription of
    that artifact: counts are primary, a provided success_rate must
    match num_success/env_num (transcription integrity check).
    SIMPLER native: gym-style envs with no central results file;
    researchers aggregate per-episode success. We ingest the natural
    per-episode export researchers already produce.
    """

    name = "simpler-libero"
    SOURCE = ("LIBERO libero/lifelong/evaluate.py eval_stats "
              "{loss, success_rate} torch.save per benchmark/task/seed; "
              "SIMPLER SimplerEnv per-episode success aggregation")
    SOURCE_URLS = ("https://github.com/Lifelong-Robot-Learning/LIBERO",
                   "https://github.com/simpler-env/SimplerEnv")
    DERIVED_DATE = "2026-10-04"

    _BENCHMARKS = ("libero_10", "libero_spatial", "libero_object",
                   "libero_goal")

    def _parse_doc(self, doc: dict) -> dict:
        if not isinstance(doc, dict):
            raise AdapterError("simpler-libero: top-level dict required")
        framework = doc.get("framework")
        if framework == "libero":
            return self._libero(doc)
        if framework == "simpler":
            return self._simpler(doc)
        raise AdapterError("simpler-libero.framework: 'libero' or "
                           f"'simpler' required, got {framework!r}")

    def _libero(self, doc: dict) -> dict:
        where = "libero"
        benchmark = doc.get("benchmark")
        if benchmark not in self._BENCHMARKS:
            raise AdapterError(f"{where}.benchmark: one of "
                               f"{self._BENCHMARKS}, got {benchmark!r}")
        task_id = _need_int(doc, "task_id", where, lo=0)
        seed = doc.get("seed")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise AdapterError(f"{where}.seed: int required, got "
                               f"{seed!r}")
        env_num = _need_int(doc, "env_num", where, lo=1)
        num_success = _need_int(doc, "num_success", where, lo=0,
                                hi=env_num)
        loss = doc.get("loss")
        if loss is not None:
            loss = _need_num(doc, "loss", where)
        rate = num_success / env_num
        claimed = doc.get("success_rate")
        if claimed is not None:
            _need_num(doc, "success_rate", where)
            if abs(claimed - rate) > 1e-9:
                raise AdapterError(
                    f"{where}: success_rate {claimed} != "
                    f"num_success/env_num {rate} (bad transcription?)")
        record = {"kind": "libero-task", "benchmark": benchmark,
                  "task_id": task_id, "seed": seed, "env_num": env_num,
                  "num_success": num_success, "success_rate": rate,
                  "loss": loss}
        return {"records": [record],
                "summary": {"n": env_num, "successes": num_success,
                            "success_rate": rate}}

    def _simpler(self, doc: dict) -> dict:
        where = "simpler"
        task = _need_str(doc, "task", where)
        variant = doc.get("variant")
        if variant not in ("visual-matching", "variant-aggregation"):
            raise AdapterError(
                f"{where}.variant: 'visual-matching' or "
                f"'variant-aggregation', got {variant!r}")
        episodes = doc.get("episodes")
        if not isinstance(episodes, list) or not episodes:
            raise AdapterError(f"{where}.episodes: non-empty list "
                               f"required")
        records = []
        for pos, ep in enumerate(episodes):
            if not isinstance(ep, dict):
                raise AdapterError(f"{where}.episodes[{pos}]: dict "
                                   f"required")
            sub = f"{where}.episodes[{pos}]"
            records.append({
                "kind": "simpler-episode", "task": task,
                "variant": variant,
                "success": _need_bool(ep, "success", sub),
                "steps": _opt_int(ep, "steps", sub, lo=0),
                "seed": _opt_int(ep, "seed", sub)})
        wins = sum(1 for r in records if r["success"])
        return {"records": records,
                "summary": {"n": len(records), "successes": wins,
                            "success_rate": wins / len(records)}}


class LeRobotEval(DerivedEval):
    """LeRobot native per-task summary + episode transcription.

    NATIVE (recorded from lerobot@8c920c42, VERIFIED 2026-10-06):
    `lerobot_eval.py::_task_info` returns {task_group, task_id,
    metrics, **success_summary}; metrics.successes is the per-episode
    bool list collected from info["is_success"] (VectorEnv final_info
    aware), and success_summary adds n_episodes, n_success,
    pc_success (percent) and pc_success_ci95 (95% Wilson, percent).
    TRANSCRIPTION (kept): strict per-episode hand export for
    researchers without the artifact at hand.
    Unknown keys are IGNORED LOUDLY (reported in provenance),
    never guessed into canonical fields.
    """

    name = "lerobot-eval"
    SCHEMA_STATUS = "VERIFIED:2026-10-06:lerobot@8c920c42"
    SOURCE = ("lerobot@8c920c42 _task_info per-task summary "
              "{task_group, task_id, metrics.successes, n_episodes, "
              "n_success, pc_success, pc_success_ci95}; eval loop "
              "success via info[\"is_success\"]")
    SOURCE_URLS = ("https://github.com/huggingface/lerobot",
                   "https://huggingface.co/docs/lerobot/adding_benchmarks")
    DERIVED_DATE = "2026-10-04"
    STATUS_NOTE = ("VERIFIED: native per-task summary recorded from "
                   "lerobot@8c920c42 (fixture + test, graduated "
                   "2026-10-06); episode transcription kept as the "
                   "strict hand-export path.")
    GRADUATED = {
        "date": "2026-10-06",
        "fixture": ("backend/adapters/fixtures/lerobot-eval/"
                    "summary_task.json"),
        "harness_commit": "8c920c4270460851cedd2737657584586d3dc66f"}

    _NATIVE_TOP = frozenset({"task_group", "task_id", "metrics",
                             "n_episodes", "n_success", "pc_success",
                             "pc_success_ci95"})
    _TRANSCRIPT_TOP = frozenset({"task", "policy", "episodes",
                                 "n_episodes"})
    _EPISODE_KEYS = frozenset({"is_success", "episode"})

    def _extra_provenance(self, parsed: dict) -> dict:
        return {"shape": parsed["shape"], "ignored": parsed["ignored"],
                "graduated": dict(self.GRADUATED),
                "review": ("second-eyes field-mapping review pending "
                           "before customer evidence cites this adapter")}

    def _parse_doc(self, doc: dict) -> dict:
        if not isinstance(doc, dict):
            raise AdapterError("lerobot-eval: top-level dict required")
        metrics = doc.get("metrics")
        native = (isinstance(metrics, dict) and "successes" in metrics)
        hand = "episodes" in doc
        if native and hand:
            raise AdapterError("lerobot-eval: native summary AND "
                               "episode transcription keys present; "
                               "send one shape")
        if native:
            return self._native_summary(doc, metrics)
        if hand:
            return self._transcription(doc)
        raise AdapterError("lerobot-eval: need native summary "
                           "(metrics.successes) or transcription "
                           f"(episodes), got keys {sorted(doc)}")

    def _native_summary(self, doc: dict, metrics: dict) -> dict:
        where = "lerobot-native"
        task_group = _need_str(doc, "task_group", where)
        task_id = _need_int(doc, "task_id", where, lo=0)
        successes = metrics.get("successes")
        if not isinstance(successes, list) or not successes:
            raise AdapterError(f"{where}.metrics.successes: non-empty "
                               f"list required")
        for pos, flag in enumerate(successes):
            if not isinstance(flag, bool):
                raise AdapterError(
                    f"{where}.metrics.successes[{pos}]: strict bool "
                    f"required, got {flag!r}")
        n = len(successes)
        wins = sum(1 for flag in successes if flag)
        n_ep = _need_int(doc, "n_episodes", where, lo=1)
        if n_ep != n:
            raise AdapterError(f"{where}: n_episodes {n_ep} != "
                               f"len(successes) {n} (bad artifact?)")
        n_su = _need_int(doc, "n_success", where, lo=0, hi=n_ep)
        if n_su != wins:
            raise AdapterError(f"{where}: n_success {n_su} != "
                               f"counted {wins} (bad artifact?)")
        pc = _need_num(doc, "pc_success", where)
        if abs(pc - 100.0 * wins / n) > 1e-6:
            raise AdapterError(
                f"{where}: pc_success {pc} != 100*n_success/"
                f"n_episodes (bad artifact?)")
        claimed_ci = doc.get("pc_success_ci95")
        lo, hi = _wilson_95(wins, n)
        if claimed_ci is None:
            ci_source = "computed"
        else:
            if (not isinstance(claimed_ci, list) or len(claimed_ci) != 2
                    or any(isinstance(v, bool)
                           or not isinstance(v, (int, float))
                           or v != v or v in (float("inf"),
                                              float("-inf"))
                           for v in claimed_ci)):
                raise AdapterError(f"{where}.pc_success_ci95: [lo, hi] "
                                   f"finite numbers required")
            if abs(claimed_ci[0] - lo) > 1e-6 or \
                    abs(claimed_ci[1] - hi) > 1e-6:
                raise AdapterError(
                    f"{where}: pc_success_ci95 {claimed_ci} != "
                    f"Wilson recompute {[lo, hi]} (bad artifact?)")
            lo, hi = float(claimed_ci[0]), float(claimed_ci[1])
            ci_source = "reported"
        ignored = {"top": sorted(set(doc) - self._NATIVE_TOP),
                   "metrics": sorted(set(metrics) - {"successes"})}
        records = [{"kind": "lerobot-episode", "task_group": task_group,
                    "task_id": task_id, "episode": pos,
                    "is_success": flag}
                   for pos, flag in enumerate(successes)]
        return {"records": records,
                "summary": {"n": n, "successes": wins,
                            "success_rate": wins / n,
                            "pc_success": pc,
                            "pc_success_ci95": [lo, hi],
                            "ci95_source": ci_source},
                "shape": "native-summary", "ignored": ignored}

    def _transcription(self, doc: dict) -> dict:
        where = "lerobot-eval"
        task = _need_str(doc, "task", where)
        policy = doc.get("policy")
        if policy is not None and (not isinstance(policy, str)
                                   or not policy):
            raise AdapterError(f"{where}.policy: non-empty string or "
                               f"null required")
        episodes = doc.get("episodes")
        if not isinstance(episodes, list) or not episodes:
            raise AdapterError(f"{where}.episodes: non-empty list "
                               f"required")
        records = []
        ep_ignored = {}
        for pos, ep in enumerate(episodes):
            if not isinstance(ep, dict):
                raise AdapterError(f"{where}.episodes[{pos}]: dict "
                                   f"required")
            sub = f"{where}.episodes[{pos}]"
            extra = sorted(set(ep) - self._EPISODE_KEYS)
            if extra:
                ep_ignored[pos] = extra
            records.append({
                "kind": "lerobot-episode", "task": task,
                "policy": policy,
                "is_success": _need_bool(ep, "is_success", sub),
                "episode": _opt_int(ep, "episode", sub, lo=0)})
        claimed_n = doc.get("n_episodes")
        if claimed_n is not None:
            _need_int(doc, "n_episodes", where, lo=1)
            if claimed_n != len(records):
                raise AdapterError(
                    f"{where}: n_episodes {claimed_n} != "
                    f"len(episodes) {len(records)} (bad transcription?)")
        wins = sum(1 for r in records if r["is_success"])
        ignored = {"top": sorted(set(doc) - self._TRANSCRIPT_TOP),
                   "episodes": ep_ignored}
        return {"records": records,
                "summary": {"n": len(records), "successes": wins,
                            "success_rate": wins / len(records)},
                "shape": "episode-transcription", "ignored": ignored}


def _stub(name: str, reason: str) -> ExternalEval:
    cls = type(f"{name}Adapter", (ExternalEval,),
               {"name": name, "STUB_REASON": reason})
    return cls()


IsaacLabArena = _stub(
    "isaac-lab-arena",
    "no public per-run export schema found; Isaac Lab logs to "
    "wandb/tensorboard with no canonical results file")
RoboArena = _stub(
    "roboarena",
    "platform-side Elo aggregation over double-blind pairwise votes; "
    "leaderboard is external-only with no public per-run export")
HalosEvidence = _stub(
    "halos",
    "Halos inspection evidence envelope shape not published; "
    "document-envelope decision stands (ingestion point reserved)")

SimplerLibero = SimplerLiberoEval()
LeRobotEval = LeRobotEval()

REGISTRY = {"isaac-lab-arena": IsaacLabArena, "roboarena": RoboArena,
            "simpler-libero": SimplerLibero, "halos": HalosEvidence,
            "lerobot-eval": LeRobotEval}


def get_adapter(name: str) -> ExternalEval:
    """Look up an adapter by registry name. Unknown names raise."""
    try:
        return REGISTRY[name]
    except KeyError:
        raise AdapterError(f"unknown adapter {name!r}; known: "
                           f"{sorted(REGISTRY)}")
    except TypeError:
        raise AdapterError(f"adapter name must be a string, got "
                           f"{name!r}")


def conformance_report() -> dict:
    """Machine-readable adapter status for CI + the NB briefing view."""
    return {"adapters": [{"name": name,
                          "schema_status": adapter.SCHEMA_STATUS,
                          "source": adapter.SOURCE,
                          "derived_date": adapter.DERIVED_DATE,
                          "stub_reason": (adapter.STUB_REASON
                                          if adapter.SCHEMA_STATUS == "STUB"
                                          else None)}
                         for name, adapter in sorted(REGISTRY.items())],
            "rule": "STUB adapters refuse parse(); DERIVED adapters parse "
                    "primary-documented shapes only (D-night-11); "
                    "VERIFIED graduation needs a recorded real-log run "
                    "(fixture + test + date)"}


def loads_json(text: str):
    """Shared strict JSON loader for adapters."""
    if not isinstance(text, str):
        raise AdapterError("log text must be a string")
    try:
        return json.loads(text)
    except ValueError as exc:
        raise AdapterError(f"log is not valid JSON: {exc}")
