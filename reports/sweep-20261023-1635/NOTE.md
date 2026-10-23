# Partial sweep (kept for honesty)

Ran on the code before commit 0b0a320. Stopped after 7 of 12: payment PASS, cart PASS, product-catalog PASS; recommendation, ad-high-cpu and homepage-flood were confidently WRONG (stale evidence from an earlier incident; accounting's chronic 15 s p95 mistaken for the incident; ad CPU spike not flagged); payment-unreachable CRASHED on Groq 429 (8,000 tokens/minute limit).

Fixes: last-hour baselines, CPU_SPIKE / CRASHED_AND_RESTARTED detection, stale-evidence rule (commit 0b0a320) and token-budget pacing in llm.py.
