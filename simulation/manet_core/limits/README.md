# Configurable hop-limit branch

Separate frozen-environment experiment. Default ring cap 16, data TTL 32, pending 3000 ms preserve parent semantics; ring cap can be 8/16/32 and data TTL 8/16/32, pending 1000¨C10000 ms. One discovery sends rings 2,4,...,cap, each bounded by original 400+80*TTL ms wait. A 32-hop ring cannot be reached within 3 s with these timers, so comparable cap tests must hold a longer pending deadline constant across variants and separately report 0.5/1/2 s on-time rates. This is not a justification to hide latency.
