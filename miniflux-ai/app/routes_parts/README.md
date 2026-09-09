# Route decomposition map

This directory is the first extraction boundary for `app/routes/scoring.py`.
The legacy blueprint remains the compatibility entry point while shared read/write
helpers are imported from `scoring` during incremental extraction. Do not move
routes by text copy without regression coverage; endpoint names and decorators
must remain unchanged.

Planned ownership:
- scores: `/api/scores`, score lists and dimensions
- diagnostics: shadow, backtest, validation, error analysis, simulation, signals
- recommendations: article/feed advice and recommendation actions
- reviews: benchmark, calibration, taxonomy and human review
- feeds: feed health, quality, advice and policy
