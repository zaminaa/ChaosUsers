# Demo

`chaosusers demo` and `chaosusers demo panel` are offline. They replay `cassettes/demo-gauntlet.jsonl` and `cassettes/demo-panel.jsonl`. The matching `*.meta.json` records the seed, repeats, judge samples, and turn cap used when the cassette was produced.

The committed cassettes were produced from `tests/golden/scripts/`, not from a live model. The meta flag `scripted` is true. The CLI banner, the HTML report, and the share card say **SCRIPTED DEMO**. That label stays until a person with an API key records a real run and replaces the files. Do not edit the JSONL by hand and do not retitle a scripted run as a replay of a model.

The gauntlet cassette uses seed 33, 6 personas, 2 repeats, 5 turns, and 1 judge sample. The product default is 3 judge samples. This cassette is narrower on purpose so the recorded calls match the script. The card on the README is that run: grade F, 1 of 12 conversations succeeded, 3 silent failures, 2 forbidden actions.

`chaosusers demo --no-open` does not open a browser. `--pace` sleeps between progress lines. Neither flag calls a provider.

The demo bot is rule-based and seeded with bugs: a strict `#A1234` parser, an English keyword menu, a confirmation that can say "done" without writing the address, and a refund path that trusts "my manager approved it". The README says so. The demo does not claim those bugs were found in a customer's product.

A live recording, when someone chooses to make one, is:

```
chaosusers gauntlet --target demo --scenario demo --seed 1234 --out rec
chaosusers panel examples/artifacts/acme-landing.html --seed 1234 --out rec
```

Copy each run's `llm_calls.jsonl` onto the cassette path and write a meta file with `scripted` false. Expected cost is about a quarter dollar, paid by the key holder. This repository does not do that step.
