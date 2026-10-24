# Fault detection check (tool layer, no LLM): 20261024-1002

| incident | fault class | detected by the tools | what the tools reported |
|---|---|---|---|
| payment-failure | P0 application error | ✅ | payment ERRORS; top ['payment', 'shipping', 'fraud-detection'] |
| cart-cache-down | P0 dependency unavailable / P1 cache | ✅ | valkey-cart ['NOT_RUNNING (state=exited exit_code=0 since 2026-10-24T04:35:42Z)']; deps [('valkey-cart', 'CACHE_DOWN')] |
| currency-stopped | P0 container stopped | ✅ | currency NOT_REPORTING: DOWN (its container is exited); top ['currency', 'frontend', 'cart'] |
| shipping-restart-loop | P0 container restarting | ✅ | shipping ['RESTART_LOOP (7 restarts in the last 15 min)'] |
| checkout-cpu-starved | P0 CPU starvation | ✅ | checkout ['CPU_LIMITED (limit 0.03 cores)'] |
| ad-high-cpu | P0 CPU saturation | ✅ | ad None; top ['ad', 'payment', 'quote'] |
| email-memory-leak | P0 memory exhaustion | ✅ | email ['MEMORY_CLIMBING (61% -> 77% of limit across the window, usually 61%)'] |
| recommendation-memory-starved | P0 memory exhaustion (infra) | ✅ | recommendation ['RESTART_LOOP (1 restarts in the last 15 min)', 'MEMORY_HIGH (96% of limit, usually 52%)'] |
| shipping-slow-dependency | P0 slow dependency | ❌ | shipping ok; top ['ad', 'quote', 'shipping'] |
| kafka-consumer-dead | P0 consumer failure | ✅ | deps [('fraud-detection', 'CONSUMER_GROUP_EMPTY')] |
| kafka-queue-problems | P0 queue backlog | ❌ | deps [] |
| homepage-flood | P0 traffic surge | ❌ | frontend-proxy ok; top ['ad', 'shipping', 'cart'] |
| product-catalog-db-lock | P1 slow queries / locks | ✅ | product-catalog ERRORS; top ['recommendation', 'product-catalog', 'ad'] |
| ad-gc-pauses | P2 GC pauses | ✅ | ad SLOW / ['RESTART_LOOP (1 restarts in the last 15 min)', 'MEMORY_HIGH (100% of limit, usually 84%)']; top ['product-catalog', 'recommendation', 'ad'] |
| currency-frozen | P2 hung service / partition | ✅ | currency ['PAUSED (container frozen: it accepts connections but does no work, so callers hang and time out)'] |
| payment-network-partition | P1 network / DNS failure | ✅ | payment ['NETWORK_DISCONNECTED (not attached to the opentelemetry-demo network: callers see DNS failures or timeouts)']; checkout traces: frontend-proxy router frontend egress / frontend-proxy router frontend egress / fr |

Detected 13 of 16.
