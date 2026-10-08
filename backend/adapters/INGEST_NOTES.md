# INGEST NOTES - OpenVLA action I/O + eval protocol (gold-standard study)

Source: tmp/mw-openvla (local clone of
https://github.com/openvla/openvla), commit
c8f03f48af692657d3060c19588038c7220e9af, dated 2025-03-23.
Studied 2026-10-06 by night-shift (Muse). No OpenVLA code is
imported or vendored; this note records what maps to our scoring.

## Action I/O (v0.1, LIBERO path)

- INPUT: one RGB image + one language prompt. The model call is
  `predict_action(**inputs, unnorm_key=..., do_sample=False)`
  where inputs = processor(prompt, image) only
  (`experiments/robot/openvla_utils.py::get_vla_action`). Prompt
  template: "What action should the robot take to <task>?"
  Proprioceptive state is assembled (`robot0_eef_pos` +
  axisangle(`robot0_eef_quat`) + `robot0_gripper_qpos`) but the
  model does NOT consume it (stated in
  `run_libero_eval.py` line 202). Greedy decode (no sampling).
- OUTPUT: 7-dim action vector (ACTION_DIM = 7 in both
  `robot_utils.py` and `openvla_utils.py`): 6-DoF delta +
  gripper, un-normalized with the checkpoint's `norm_stats`
  keyed per task suite (`unnorm_key = task_suite_name`, with a
  `_no_noops` fallback). For LIBERO execution the gripper lane
  is binarized [0,1] -> [-1,+1] then sign-flipped
  (`normalize_gripper_action`, `invert_gripper_action`).
- Image preprocessing: resize (model-specific) + optional
  center-crop at 0.9 scale when the checkpoint trained with
  augmentations (crop dims scale by sqrt(0.9)).

## Eval protocol A: LIBERO sim (the machine-readable one)

File: `experiments/robot/libero/run_libero_eval.py`.

- Suites: libero_spatial / object / goal / 10 / 90. Per task:
  `num_trials_per_task` rollouts (default 50) from the suite's
  canonical init states; per-suite step caps 220/280/300/520/400
  plus 10 no-op wait steps for sim settling.
- SUCCESS SIGNAL: the LIBERO env `done` flag (sim task
  predicate). No human in the loop. Exceptions abort the
  episode and count as failure (no retry).
- ARTIFACTS: local text run log
  (`EVAL-<suite>-<family>-<DATETIME>[--note].txt`: per-episode
  "Success: True/False" + running counts + per-task and total
  rates) plus optional wandb (`success_rate/<task>`,
  `num_episodes/<task>`, `success_rate/total`,
  `num_episodes/total`). There is NO JSON summary artifact:
  an adapter ingests a TRANSCRIPTION of the run log (same
  precedent as our LIBERO torch.save and LeRobot hand paths).
- Seed: full seeding (`set_seed_everywhere`, default 7)
  including PYTHONHASHSEED.

## Eval protocol B: Bridge real robot (NOT machine-readable)

File: `experiments/robot/bridge/run_bridgev2_eval.py`.

- Interactive WidowX rollouts: the operator types each task
  label, presses Enter per episode, Ctrl-C to abort, 'r' to
  redo. max_steps 60 at configured control frequency.
- SUCCESS SIGNAL: none in code. No `done` flag, no success
  log lines, no summary. Success is judged by the operator
  offline. Optional `save_data` persists per-episode
  (images, states, actions) via `save_rollout_data` plus a
  replay video. Any success-rate claim over Bridge rollouts
  is an OPERATOR transcription, never a harness output.
  An adapter MUST label that provenance accordingly.

## What maps to our scoring

- LIBERO `done` per episode -> our success counting (same
  role as LeRobot `is_success`): feeds runs/evaluate verdict
  inputs and any future success-rate gate. Per-task rates
  with n>=50 suit Wilson intervals (same math as lerobot-eval).
- 7-dim action vectors + per-step states (Bridge save_data,
  LIBERO obs) -> our trace pairs (commanded vs actual):
  drift/horizon, Frechet, action-sensitivity gates apply
  once a transcription pins commanded-vs-actual columns.
- Step caps + wait steps + greedy decode + seed -> ODD /
  reproducibility metadata on the PAR, not scored fields.
- No proprio input to the policy is itself a reviewable
  claim for sensitivity analysis (action marginalization
  lens): the policy cannot react to contact it never sees.

## Adapter recommendation (not yet built)

- `openvla-libero`: STUB today is correct. Graduation path is
  a strict transcription of the LIBERO run log: {task_suite,
  task, trials: [bool...], seed?, max_steps?} with the same
  count/rate cross-checks as lerobot-eval. Wandb-only runs
  are second-class evidence (no local log to transcribe).
- `openvla-bridge`: only as OPERATOR-TRANSCRIBED, with the
  auditor name captured and no harness-success claim. Do not
  build until a customer brings labeled rollouts.
- Never import prismatic/torch: JSON transcription at the
  adapter edge, same as every other harness.
