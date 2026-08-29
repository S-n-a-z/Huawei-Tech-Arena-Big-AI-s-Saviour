# Architecture-aware resilience extension

## Purpose and boundary

Phase 1 is scored on county-level outage-ratio forecasts. The submitted `predictions.csv` therefore ends at regional risk and does not use power-network topology or data-centre backup configuration. This extension is retained to show how the forecasting work can develop into a useful resilience decision aid without changing the scored path.

The extension is not a claim that the current illustrative parameters describe a real site. Its outputs are unscored research indicators and must be reviewed by a qualified electrical engineer before any operational use.

## Proposed flow

1. The validated Task A or Task B model produces a regional outage-risk trajectory.
2. A site adapter links the county or network region to the relevant utility connection and, where available, feeder or substation context.
3. A versioned site-architecture record supplies reviewed configuration data.
4. A deterministic resilience layer estimates site-risk, protected-load coverage and backup endurance for each forecast lead.
5. The interface reports both the estimate and its assumptions; missing or unverified site fields fail validation rather than being silently imputed.

This separation keeps the machine-learning forecast auditable and allows engineering assumptions to be changed without retraining the outage model.

## Site inputs

The JSON schema in `configs/site_architecture.schema.json` defines the proposed exchange format. The most important inputs are:

- a stable site and architecture identifier;
- critical IT load and the fraction that must remain protected;
- usable battery energy after derating, not nameplate energy;
- generator endurance and fuel assumption;
- redundancy class and the number of independent utility feeds;
- transfer time and maintenance state;
- parameter provenance, review status and review date.

The present TOML values remain convenient examples for exercising the older Phase 2 code. Their status is `illustrative_unscored_baseline_requires_site_review`.

## Validation gates before use

- Confirm that units, derating rules and time bases are consistent.
- Reject negative values and coverage fractions outside `[0, 1]`.
- Record the source and reviewer for every site-specific parameter set.
- Test common-mode failures; nominal `2N` labels alone do not establish independence.
- Compare predicted endurance with commissioning or maintenance evidence where available.
- Calibrate regional-to-site risk using matched historical site events before interpreting the output as a probability.
- Keep scored Phase 1 files independent of this layer unless a later organiser instruction explicitly changes the task.

## Data sources and licensing

The retained UK research adapters use SSEN Distribution NaFIRS and substation datasets under CC BY 4.0, plus optional OpenStreetMap data under ODbL 1.0. Those sources, their roles and their official links are recorded in `SOURCES.md`. They are not used as US Phase 1 labels and cannot be transferred across geography without a separate validation study.

## Practical next experiment

A useful follow-on would pair one fully reviewed, synthetic site configuration with the frozen county forecast and run a sensitivity analysis over battery derating, generator endurance and common-mode feed loss. The output should be a range rather than a single apparently precise number. That would test the interface and decision logic without presenting illustrative configuration values as measured facts.
