# Persona pack spec

A pack is a folder: `pack.yaml`, `lexicon.yaml`, and `personas/<id>.yaml`. It holds behavior classes, never real people.

`pack.yaml` names the id, version, language, license, optional `extends`, provenance, and `language_instructions`. An overlay with `extends: core-en` inherits every persona. A file with the same id is deep-merged: dictionaries merge, lists and scalars replace.

Every persona cites a taxonomy class, lists the modes it can run, and includes an example utterance that passes its own fidelity rules. See `packs/core-en` and `packs/core-fa`.

Validate with `chaosusers packs validate <id-or-path>`.
