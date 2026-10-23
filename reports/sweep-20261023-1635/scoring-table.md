| incident | expected | agent_said | fault_type | confidence | evidence_real | schema_valid | tool_calls | seconds | verdict |
|---|---|---|---|---|---|---|---|---|---|
| payment-failure | payment | payment | application_error | high 0.85 | yes (3 cited, registry-checked) | yes | 4 | 49.2 | PASS |
| cart-failure | cart | cart | dependency_unreachable | medium 0.62 | yes (2 cited, registry-checked) | yes | 8 | 136.9 | PASS |
| product-catalog-failure | product-catalog | product-catalog | application_error | medium 0.6 | yes (3 cited, registry-checked) | yes | 7 | 94.6 | PASS |
| recommendation-cache-leak | recommendation | cart | dependency_unreachable | high 0.85 | yes (3 cited, registry-checked) | yes | 8 | 153.6 | WRONG (confident!) |
| ad-high-cpu | ad | accounting | latency | high 0.85 | yes (2 cited, registry-checked) | yes | 8 | 78.1 | WRONG (confident!) |
| homepage-flood | frontend | accounting | latency | high 0.85 | yes (2 cited, registry-checked) | yes | 7 | 67.7 | WRONG (confident!) |
| payment-unreachable | payment | CRASH | - | - | - | - | - | - | CRASH: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gp |

PASS 3/7 · escalated 0 · confidently wrong 3
