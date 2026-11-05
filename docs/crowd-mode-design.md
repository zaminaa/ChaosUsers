# Crowd mode (not built in v0.1)

Hundreds to thousands of lightweight reactions to a launch artifact.

- Population, not personas: a future `population.yaml` lists a persona id, a weight, and jitter ranges. A crowd member is a persona instance plus sampled jitter. The `overrides` field already exists and stays empty until then.
- Reaction, not conversation: one cheap call per member using the Panel prompt, with findings capped at 2. The batch is checked against the budget before it starts.
- Same outputs: results aggregate into panel scores grouped by behavior class and produce the same location and occurs predictions. There is no new receipt format, so `verify` stays the same.
