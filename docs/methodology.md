# Methodology

ChaosUsers runs synthetic users against a product before launch. It reports where a flow breaks. It does not estimate what share of a real population will do the same thing.

The behavior classes were distilled from years of production support patterns in a conversational assistant used daily by non-technical staff. A class describes what people do. Packs hold no real user records, no employer names, and no contact details.

## Architecture

One Python package, five layers:

1. **Persona packs.** YAML only. `packs/taxonomy.yaml` lists behavior classes. `packs/<id>/` holds metadata, a lexicon, and one file per persona.
2. **Persona engine.** Generic code. Text operators, a patience state machine, and fact memory turn pack data into behavior. No persona id is hardcoded in `chaosusers/`.
3. **Mode runners.** Gauntlet talks to a target for several turns. Panel has each persona read an artifact once. Both are bounded by `max_turns`, a USD cap, and a finite worker pool.
4. **Scorers.** Deterministic checks run first. A blind judge may then explain the transcript. The judge never sets the grade.
5. **Recorder.** Each run writes a directory: manifest, transcripts or panel responses, scores, predictions, and a report. The predictions file is the receipt.

Every model call goes through `chaosusers.llm.client.LLMClient`. Providers, the scripted provider, and the replay provider all sit behind that one object. A reservation is taken **before** the HTTP call. If the reservation would cross the cap, the call is not made.

Data files live at the repo root (`packs/`, `prompts/`, `rubrics/`, `scenarios/`, `examples/`, `cassettes/`). An installed wheel copies them under `chaosusers/_data/`. `data_root()` picks `_data` when that directory exists, and the repo root otherwise.

## The judge does not grade

The headline grade is computed only from deterministic outcomes. End-state checks and a few transcript patterns decide success, silent failure, forbidden action, abandonment, stuck, incomplete, unverified, or error. The mapping lives in `chaosusers/gauntlet/score.py` (`classify_outcome`, `compute_grade`) and the thresholds live in `rubrics/grade_v1.yaml`.

The judge is a separate pass:

- It receives the transcript only. The prompt in `prompts/judge_gauntlet_v1.md.j2` has no persona name, archetype, class id, mood, or check result.
- It must quote the turn it relies on. `judge_transcript` keeps a quote only when the normalized quote is a substring of that same turn. Other judgments are dropped and counted.
- It is sampled more than once. The label kept for a dimension is the majority of grounded samples. If no label has more than half, the consensus is `uncertain`.
- When the consensus disagrees with the deterministic outcome, the report lists the disagreement. The grade is not averaged and not moved.

Panel mode has no judge. The persona is the instrument. A finding counts only when its quote is at least three words and appears in the text that persona was actually shown.

## Silent failure

A silent failure is one conversation where both of these are true:

1. Some bot turn matches the scenario's `success_claim` (the bot told the user the task was done).
2. At least one evaluable **success** check failed (the end state says it was not done).

The outcome is assigned only if a stricter rule did not already fire. The order in `classify_outcome` is:

1. `budget_exhausted` or `target_error` → **error**
2. any forbidden check with `passed is False` → **forbidden_action**
3. every evaluable success check passed → **success**
4. evaluable success checks exist, at least one failed, and the bot claimed success → **silent_failure**
5. no success check could be evaluated → **unverified**
6. the user abandoned → **abandoned**
7. the turn cap was hit → **stuck**
8. otherwise → **incomplete**

`passed: null` means the check could not be evaluated. It is not treated as false. A black-box target with no state and no transcript success check is unverified, not a silent failure.

The grade file caps the letter at C when any conversation is a silent failure, and at D when any critical forbidden check fails. Those caps are reasons printed beside the grade. They are not judge opinions.

## Receipt and verify

`predictions_from_gauntlet` and `predictions_from_panel` write only two kinds of claim:

- **location** — a step or section will be among the top drop-off points.
- **occurs** — a named failure will happen at least once (silent failure, forbidden action, a persona blocked at a step, or a misread).

There is no rate claim. The set is capped at ten items, ordered by confidence, and numbered `P-001` upward.

`canonical_sha256` hashes the canonical JSON of that set (`sort_keys`, compact separators, UTF-8). The hash is stored on the manifest as `predictions_sha256` and printed as the receipt. The recorder does not write the secret values of headers. Placeholders such as `${ENV_VAR}` stay in the manifest.

`chaosusers verify <run> --observed observed.yaml` reads the receipt and the observed file. It does not rewrite `predictions.json` or the manifest.

- A **location** claim is confirmed if its step is inside `dropoff_ranking[:top_k]`, refuted if the step appears later in that ranking, and untested otherwise.
- An **occurs** claim is confirmed or refuted from `occurrences[id]`, and untested if the id is absent.
- `receipt_intact` is true only when hashing the predictions file still equals `manifest.predictions_sha256`.
- Precision is confirmed / (confirmed + refuted). If nothing was tested, precision is null.

The command writes `verification.json` and re-renders the report. A mismatched `run_id` is a warning. The check still runs.

## Cost and the reservation

`Budget.reserve(est_in, max_out)` runs before `provider.complete`. The estimate is the reserved input tokens plus the request's `max_tokens` output ceiling, priced from `pricing.yaml` per million tokens. Outstanding reservations count. A second in-flight call can be refused even when nothing has been committed yet. `commit` replaces the reservation with the measured token counts and the actual USD. `release` drops the reservation when the call fails or when the response is a free replay or script (`cached: true`).

`max_usd` must be greater than zero. An unpriced model is allowed only with `--allow-unpriced`, and then only the token cap applies. A run that hits the cap stops starting new conversations, keeps the units that already finished, and writes the report with status `budget_exhausted`.

Prices in `pricing.yaml` are inputs to that arithmetic. Each row is either commented with the page and date it was checked, or marked `TODO` when it has not been checked. Unmarked numbers are not a guess added on top. The checked-in numbers are the ones the tests lock. See the file header before a release.

## Language packs

A pack is behavior data. `core-en` is the base. `core-fa` is an overlay: `extends: core-en`, Persian voice lines, and `fidelity.require_script: Arabic` on the translated personas. `romanized-typer` stays Finglish and is not overridden. Deep merge copies dictionaries recursively and replaces lists and scalars. The gauntlet block of a translated persona is inherited, so patience numbers do not drift between languages.

The file format, operator list, and the four steps for a new language are in [persona-pack-spec.md](persona-pack-spec.md). `chaosusers packs validate <id>` is the gate. Example utterances must pass the persona's own fidelity rules.
