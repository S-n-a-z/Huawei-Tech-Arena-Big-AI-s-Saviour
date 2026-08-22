# Working together

Please keep changes small enough to review and explain the reason for them in the commit message. Data preparation, modelling and the architecture calculation are separate parts of the pipeline, so changes to one stage should not silently alter another.

Before opening a pull request:

1. Run `python -m pytest`.
2. If modelling code changed, rebuild the affected task and record the new chronological validation result.
3. Run `python -m tech_arena validate` after exporting predictions.
4. Update the report if a metric, data source, assumption or limitation changed.
5. Do not commit raw third-party downloads, credentials or private challenge inputs.

Use British English in documentation. Prefer direct descriptions of what the code does and be explicit when a value is an assumption rather than a challenge-supplied parameter.
