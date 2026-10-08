# lerobot-eval fixture: native per-task summary

Shape mirrors `lerobot_eval.py::_task_info` exactly: one per-task entry
with the raw per-episode metrics plus the task's success count and
interval (`task_group`, `task_id`, `metrics`, `**success_summary`).

- Source: tmp/mw-lerobot (local clone of
  https://github.com/huggingface/lerobot), commit
  8c920c4270460851cedd2737657584586d3dc66f, dated 2026-10-03.
- Pinned code: `src/lerobot/scripts/lerobot_eval.py` (`_task_info`,
  `eval_policy`, `eval_policy_all`; per-env `is_success` collection at
  rollout lines 329-357) and `src/lerobot/utils/eval_stats.py`
  (`success_summary`: `n_episodes`, `n_success`, `pc_success` percent,
  `pc_success_ci95` 95% Wilson bounds in percent).
- Capture date: 2026-10-06. Capturer: night-shift (Muse).
- SECURITY: values are SYNTHETIC (6/10 successes invented for the
  fixture); the SHAPE and the interval math are real. `pc_success`
  is 60.0 and `pc_success_ci95` holds the true Wilson bounds for
  6/10 computed from lerobot's own formula (verified against its
  docstring example 9/10 -> 0.596/0.982 before embedding).
- No customer logs. No lerobot package import: the adapter reads a
  JSON transcription of the native artifact (same precedent as the
  LIBERO torch.save transcription), so core stays dependency-free
  and pyarrow (if ever needed) stays at the adapter edge only.
