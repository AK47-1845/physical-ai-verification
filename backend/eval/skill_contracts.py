"""Skill-contract scorer + task-graph ingest (orchestrator surface).

Skills (SkiROS2, Cortex primitives, fleet planners) expose contracts:
pre-conditions on entry state, post-conditions on exit state, invariants
over the trace. We score contracts against recorded state traces:
perfect gate fodder, and we build no orchestrator ourselves.

Task graphs (planner outputs) ingest as validated DAGs with a
deterministic topological order; the ordered chain becomes PAR
ingredient lineage. Cycles and dangling edges are rejected loudly:
a graph we cannot order is a graph we cannot trust.
"""

from collections import deque

from engine import InputError


class SkillContractError(InputError):
    """Contract + graph failures. Loud by design (authoring bugs)."""


def _is_bool(v) -> bool:
    return isinstance(v, bool)


def check_skill(contract: dict, states: list) -> dict:
    """Score one skill contract against a state trace (list of dicts)."""
    if not isinstance(contract, dict):
        raise SkillContractError("contract: dict required")
    skill_id = contract.get("skill_id")
    if not skill_id or not isinstance(skill_id, str):
        raise SkillContractError("contract.skill_id: non-empty string")
    for key in ("pre", "post"):
        if not callable(contract.get(key)):
            raise SkillContractError(f"contract.{key}: callable required")
    invariant = contract.get("invariant")
    if invariant is not None and not callable(invariant):
        raise SkillContractError("contract.invariant: callable or None")
    if not isinstance(states, (list, tuple)) or not states:
        raise SkillContractError("states: non-empty sequence required")
    states = list(states)
    for i, state in enumerate(states):
        if not isinstance(state, dict):
            raise SkillContractError(f"states[{i}]: dict required")
    try:
        pre = contract["pre"](states[0])
        post = contract["post"](states[-1])
    except Exception as exc:
        raise SkillContractError(f"predicate raised: {exc!r}")
    if not _is_bool(pre) or not _is_bool(post):
        raise SkillContractError("pre/post must return bool")
    inv_holds, failing_index = None, None
    if invariant is not None:
        inv_holds = True
        for i, state in enumerate(states):
            try:
                ok = invariant(state)
            except Exception as exc:
                raise SkillContractError(
                    f"invariant raised at index {i}: {exc!r}")
            if not _is_bool(ok):
                raise SkillContractError(
                    f"invariant must return bool (index {i})")
            if not ok:
                inv_holds = False
                failing_index = i
                break
    holds = pre and post and (inv_holds is not False)
    return {"skill_id": skill_id, "pre": pre, "post": post,
            "invariant": inv_holds, "failing_index": failing_index,
            "holds": holds, "states": len(states)}


def ingest_task_graph(graph: dict) -> dict:
    """Validate a task DAG; return deterministic order + PAR chain."""
    if not isinstance(graph, dict):
        raise SkillContractError("graph: dict required")
    nodes = graph.get("nodes")
    edges = graph.get("edges", [])
    if not isinstance(nodes, list) or not nodes:
        raise SkillContractError("graph.nodes: non-empty list required")
    if not isinstance(edges, list):
        raise SkillContractError("graph.edges: list required")
    ids = []
    by_id = {}
    for node in nodes:
        if (not isinstance(node, dict) or not node.get("id")
                or not isinstance(node.get("id"), str)):
            raise SkillContractError("every node needs a string id")
        if node["id"] in by_id:
            raise SkillContractError(f"duplicate node id {node['id']!r}")
        ids.append(node["id"])
        by_id[node["id"]] = node
    successors = {i: [] for i in ids}
    indegree = {i: 0 for i in ids}
    for edge in edges:
        if (not isinstance(edge, (list, tuple)) or len(edge) != 2):
            raise SkillContractError(f"edge must be a [from, to] pair: {edge!r}")
        src, dst = edge
        if not isinstance(src, str) or not isinstance(dst, str):
            raise SkillContractError(
                f"edge endpoints must be str ids: {edge!r}")
        if src not in by_id or dst not in by_id:
            raise SkillContractError(f"edge {edge!r} dangles off the graph")
        successors[src].append(dst)
        indegree[dst] += 1
    ready = deque(sorted(i for i in ids if indegree[i] == 0))
    order = []
    while ready:
        node = ready.popleft()
        order.append(node)
        for nxt in sorted(successors[node]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
        ready = deque(sorted(ready))
    if len(order) != len(ids):
        raise SkillContractError("task graph has a cycle; cannot order")
    chain = [{"task": i, "skill": by_id[i].get("skill_id"),
              "status": by_id[i].get("status", "UNKNOWN")} for i in order]
    return {"order": order, "ingredient_chain": chain,
            "nodes": len(ids), "edges": len(edges)}


def _grasp_pre(state):
    return state.get("gripper_open") is True


def _grasp_post(state):
    return state.get("holding") is True


def _release_pre(state):
    return state.get("holding") is True


def _release_post(state):
    return (state.get("gripper_open") is True
            and state.get("holding") is False)


PRESET_CONTRACTS = {
    "grasp": {"skill_id": "grasp", "pre": _grasp_pre,
              "post": _grasp_post,
              "about": "pre: gripper_open is True on entry; post: "
                       "holding is True on exit"},
    "release": {"skill_id": "release", "pre": _release_pre,
                "post": _release_post,
                "about": "pre: holding is True on entry; post: "
                         "gripper_open is True and holding is False"},
}


def get_preset_contract(contract_id: str) -> dict:
    """Look up a preset skill contract. Custom predicates stay
    library-only (callables cannot cross HTTP honestly)."""
    if not isinstance(contract_id, str) or contract_id not in PRESET_CONTRACTS:
        raise SkillContractError(
            f"contract_id: unknown preset {contract_id!r}; known: "
            f"{sorted(PRESET_CONTRACTS)} (custom contracts are "
            f"library-only)")
    preset = PRESET_CONTRACTS[contract_id]
    return {"skill_id": preset["skill_id"], "pre": preset["pre"],
            "post": preset["post"]}
