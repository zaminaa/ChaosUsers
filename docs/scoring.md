# Scoring

The grade is computed from deterministic end-state checks. The judge only explains.

A conversation is a success only when every evaluable success check passes. If the bot claimed success and a check failed, that is a silent failure. A failed forbidden check outranks that. Error and unverified runs do not enter the success rate. Critical forbidden actions cap the grade at D. Any silent failure caps it at C. If nothing could be checked, the run is UNGRADED.

Details live in `rubrics/grade_v1.yaml` and `rubrics/gauntlet_v1.yaml`. Their hashes are stored in each run manifest.
