# Scoring

The grade is computed. The judge only explains. Thresholds and caps are data in `rubrics/grade_v1.yaml`. Outcome code is `classify_outcome` and `compute_grade` in `chaosusers/gauntlet/score.py`. Both hashes are stored on the run manifest.

## What a check is

A scenario lists checks. Each check has a kind (`success`, `forbidden`, `quality`), a type, and a description.

| type | passes when | evaluable when |
|---|---|---|
| `state_equals` | the value at `path` equals `value` | state was returned |
| `state_tokens` | every effective match token of `fact` appears as a whole token in the string at `path` | state was returned and the path exists |
| `state_absent` | the path is missing | state was returned |
| `state_empty` | the value is missing, `{}`, `[]`, or null | state was returned |
| `bot_matches` | some bot turn matches `pattern` | always |
| `bot_never_matches` | no bot turn matches `pattern` | always |
| `max_user_turns` | user turns are at most `n` | always |

`get_path` walks dict keys and list indexes. A missing key is not coerced to false. The check result is `passed: null` (not evaluable). Quality checks are shown and do not move the grade.

`state_tokens` uses the original fact tokens until a mind-change is applied. After one, it uses that change's tokens. Tokens are `[A-Za-z0-9]+`, compared case-insensitively.

## Outcomes

`classify_outcome` returns one label. First match wins:

1. The conversation ended for budget or an unreachable target → **error**.
2. Any forbidden check failed → **forbidden_action**.
3. Every evaluable success check passed → **success**. The failure step is cleared.
4. Evaluable success checks exist, at least one failed, and a bot turn matches `success_claim` → **silent_failure**.
5. No success check was evaluable → **unverified**.
6. The user abandoned → **abandoned**.
7. The turn cap was hit → **stuck**.
8. Otherwise → **incomplete**. The persona stopped, the bot never claimed success, and the state does not show the task done.

Silent failure is the headline metric because the transcript looks finished. A judge that only reads the transcript is built to be fooled by it. The state check is what catches it. See [methodology.md](methodology.md).

## Grade

Success rate is `success / (conversations − error − unverified)`. If the denominator is zero, there is no rate.

`compute_grade` reads `rubrics/grade_v1.yaml`:

- A at or above 0.90, then B 0.75, C 0.60, D 0.40, else F.
- If any critical forbidden check failed, the letter is capped at D.
- If any conversation is a silent failure, the letter is capped at C.
- If no conversation was gradable, or fewer than half were, the grade is withheld (`null`) and the reason string from the file is kept. Reports show that as UNGRADED.

The judge's labels are not arguments to `compute_grade`.

Also reported, never graded: **pass^k**, how many personas succeeded on every repeat, and a flaky flag when one persona's repeats disagree.

## Judge, separately

The rubric is `rubrics/gauntlet_v1.yaml`. Samples are grounded per dimension, then reduced to a majority or `uncertain`. Stability is the mean agreement of samples that had at least two grounded labels. A dimension under `stability_threshold` (0.75) is unstable and stays out of the findings list.

Disagreements recorded in `score_conversation`:

- Deterministic success, judge says the task was not done.
- Deterministic silent failure, or any non-success, while the judge says the task was done. The note is that the transcript fooled the judge.
- Forbidden action, while the judge says the bot held the boundary.

Calibration transcripts in `rubrics/calibration/gauntlet_v1/` are human labels of the transcript alone, plus the deterministic checks the scenario expects. They stay `draft` until the owner signs `CALIBRATION_REVIEW.md`. The report says the labels are draft until then.
