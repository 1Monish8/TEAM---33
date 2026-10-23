# Aborted sweep (kept for honesty)

Stopped after 2 of 12 incidents: a second copy of the demo was started mid-run and recreated Jaeger/Prometheus, wiping trace and metric history. Results below are valid for the 2 incidents that finished before that.

- payment-failure: PASS (payment, high)
- cart-failure: WRONG (said astronomy-db; Postgres was mistaken for redis). Led to the infrastructure-map + "blame a dependency only if it is unhealthy" rule in the prompt.
