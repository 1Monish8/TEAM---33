# Day 2 after-sweep (final code at the time; quota-limited)

8 of 12 incidents completed before both Groq models hit their 200k tokens/day caps; most calls ran on the fallback gpt-oss-20b (see each transcript's llm_reply "model"). kafka-queue-problems was discarded: it ran while checkout was still CPU-starved by a practice-reset bug (fixed). Not run: homepage-flood, recommendation-cache-leak, ad-high-cpu.
