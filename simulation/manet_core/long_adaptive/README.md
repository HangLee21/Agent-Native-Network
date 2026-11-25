# Six-hour resource sampling variant

Adds `host_resource` read-only snapshots every 60 seconds of simulated time. Per-node values: active routes, active discoveries, pending business, unexpired RREQ dedup entries, output queue, event queue, SDK peer cache, and inflight frame. It does not send packets or change node decisions. Equality to the unsampled engine must be verified on a controlled run before inference. Sampling can miss instantaneous peaks and is not a board heap/stack measurement.
