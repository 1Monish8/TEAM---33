| incident | expected | agent_said | fault_type | confidence | reviewer | evidence_real | schema_valid | tool_calls | seconds | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| payment-failure | payment | payment | application_error | low 0.45 | - | yes (3 cited, registry-checked) | yes | 4 | 249.4 | ESCALATED |
| cart-failure | cart | valkey-cart | resource_exhaustion | medium 0.6 | disputed | yes (2 cited, registry-checked) | yes | 6 | 371.2 | PASS |
| product-catalog-failure | product-catalog | product-catalog | resource_exhaustion | medium 0.6 | disputed | yes (2 cited, registry-checked) | yes | 4 | 247.2 | PASS |
| payment-unreachable | payment | None | unknown | low 0.2 | - | yes (0 cited, registry-checked) | yes | 12 | 802.8 | ESCALATED |
| currency-stopped | currency | currency | service_down | medium 0.7 | confirmed | yes (3 cited, registry-checked) | yes | 3 | 186.2 | PASS |
| cart-cache-down | valkey-cart | frontend-proxy | application_error | medium 0.6 | disputed | yes (1 cited, registry-checked) | yes | 4 | 250.9 | WRONG |
| shipping-restart-loop | shipping | kafka | restart_loop | medium 0.6 | disputed | yes (3 cited, registry-checked) | yes | 4 | 188.7 | WRONG |
| checkout-cpu-starved | checkout | checkout | resource_exhaustion | high 0.9 | confirmed | yes (3 cited, registry-checked) | yes | 6 | 1976.3 | PASS |

PASS 4/8 · escalated 2 · confidently wrong 0
