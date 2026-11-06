# Crowd mode

Not built in v0.1. The design is here so a later version does not invent a second receipt.

A crowd is a population, not a new kind of persona. A future `population.yaml` would list `{persona_id, weight, jitter}`. Jitter ranges apply to fields that already exist, such as `gauntlet.patience.start` or `gauntlet.fact_drift`. A member is a `PersonaInstance` with those overrides filled in. In v0.1 `overrides` exists and stays `{}`.

The reaction is one cheap Panel call per member, with findings capped at 2. The batch is reserved against `Budget` before any call is sent. There is no conversation loop and no new judge.

Results aggregate into the same panel scores, grouped by behavior class, and emit the same `location` and `occurs` predictions. `chaosusers verify` does not grow a new file format. Until this exists, the command surface does not advertise a crowd date.
