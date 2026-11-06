# Persona pack spec

A pack is a folder of YAML. It contains behavior classes, not people and not production logs. ChaosUsers ships `packs/core-en` (the base) and `packs/core-fa` (a Persian overlay). Copy the overlay when you add a language.

```
packs/<pack-id>/
  pack.yaml
  lexicon.yaml
  personas/<persona-id>.yaml
packs/taxonomy.yaml
```

Validate with:

```
chaosusers packs validate core-fa
chaosusers packs validate packs/my-lang
```

`packs show <persona-id> --pack <id>` prints the merged persona. Invalid personas are not skipped.

## pack.yaml

Required fields: `id` (kebab-case), `version`, `title`, `language`, `license`, `provenance`, `language_instructions`. `extends` is `null` or another pack id.

`language_instructions` maps a BCP-47 tag to one sentence the persona must obey. `core-fa` keeps the English and Finglish lines and sets `fa` to informal Persian in Persian script.

Provenance stays generic. Do not name an employer, a product, or a person. The sentence used in this repo is: distilled from years of production support patterns in a conversational assistant used daily by non-technical staff.

## lexicon.yaml

`apology_phrases` is what the `apology_prefix` operator may prepend. `examples_by_language` is extra few-shot text for a language tag. Phrase lists do not belong in Python.

## Persona file

Required: `id`, `name`, `archetype`, `behavior_class`, `language`, `summary`, `voice`, `modes`. `behavior_class` must exist in `packs/taxonomy.yaml`. `language` must be a key of the pack's `language_instructions`. `id` is kebab-case.

`modes` is `panel`, `gauntlet`, or both. If a mode is listed, its block is required.

`voice` has `register`, `vocabulary_level` (`plain`, `everyday`, or `technical`), `typical_phrases`, `never`, and `example_utterance`. The example must pass this persona's fidelity rules. That is checked when the fidelity module is present, which it is in this package.

`fidelity`:

- `max_words`: maximum whitespace tokens, or null.
- `require_script`: `any`, `Latin`, or `Arabic`. Arabic means at least one letter in U+0600–U+06FF when the text has letters. Latin means none of those letters.
- `forbidden_words`: whole word, case-insensitive. `SSO` matches, `lasso` does not.

### Gauntlet block

`reading_budget_words` is the length that fires `bot_long`. `fact_drift` is in `[0, 1]`. For each fact, in name order, the seeded RNG either keeps `fact.value` or picks one of `fact.variants`.

`patience` starts at `start`. Each event subtracts `costs` and adds `recovery`, then the value is capped at `start`. Mood is angry below `angry_below`, frustrated below `frustrated_below`, otherwise calm. The user abandons when the value is at or under `abandon_at`. `on_abandon` is `leave`, `block`, `go_silent`, or `demand_human`. Order must be `angry_below ≤ frustrated_below ≤ start`.

Operators run in order on the model draft. Mood skips do not draw a random number. Every other operator draws once for `p`.

| op | effect |
|---|---|
| `max_words` | keep the first `n` whitespace tokens |
| `lowercase` / `uppercase` | change case |
| `strip_punctuation` | drop `. , ; : ! ?` and keep `#` |
| `exclaim` | append `!!` unless the text already ends with `!` |
| `typos` | for each alphabetic token of length ≥ 4, with probability `rate`, swap, drop, or double one inner letter. Digits and `#A1001` are not tokens of that kind. |
| `apology_prefix` | prepend a random lexicon apology and a space |

`mind_change` and `scope_push` are optional. They fire from the scenario's lists, not from persona-specific code.

### Panel block

`reading.mode` is `full` or `skim`. Skim keeps the first `words_per_section` words of ordinary text, keeps every `[BUTTON: …]`, `[FIELD: …]`, and `[CHECKBOX …]` marker, and appends an ellipsis if the prose was cut. `attention_focus`, `abandon_triggers`, and `extra_instructions` are prompt data.

## Overlays

`extends: core-en` inherits every persona. A file with the same id is deep-merged over the base. Dictionaries merge recursively. Lists and scalars replace. The base dict is copied first. It is not mutated.

`packs/core-fa/personas/apologetic-novice.yaml` is the pattern: `id`, `language: fa`, `voice.typical_phrases`, `voice.example_utterance`, and `fidelity.require_script: Arabic`. It does not copy the gauntlet numbers. Those stay inherited, so a Persian Pat and an English Pat share one patience model.

`romanized-typer` is already Finglish (`fa-Latn`). The Persian overlay does not replace that file.

A cycle in `extends` is a `PackError`. So is an unknown class, a language missing from `language_instructions`, an email, a URL, or a phone-like digit run.

## A new language

1. Copy `packs/core-fa` to `packs/core-xx`.
2. Set `id` and `language`, and add one `language_instructions` line.
3. Translate `voice.typical_phrases`, `voice.example_utterance`, and `lexicon.yaml`. Leave gauntlet numbers alone unless you mean to change behavior.
4. Run `chaosusers packs validate packs/core-xx`.

Class ids BC10–BC12 have no persona yet. A proposal should cite the class, follow its `respect_note`, and avoid real names.
