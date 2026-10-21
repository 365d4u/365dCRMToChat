# Snapshot consumer throughput optimization — 2026-10-21

User authorized optimizing publication-to-projection latency following the Aliyun-only cutover. Deploy from a pushed main commit; only `crm_to_chat/consume.py` changes on production. Preserve server media.py, writer/contracts, environment, unit/limits, workspace1, one serial writer and the masked retired tunnel.

## Evidence and change

At 19:48 Beijing, PID3015086 projected 599 events in 60 seconds. It used prefetch1, a nonblocking I/O pump and an unconditional 50ms sleep. Bounded read-only MySQL checks measured SELECT1 median0.117ms and one indexed conversation aggregate0.807ms; these are samples, not all-write latency measurements. Natural snapshot samples at19:57 still lacked receipts, indicating queueing under current load; earlier cutover samples took41–46s.

Prefetch8 now buffers a bounded transport window while preserving serial transactional writes. The connected loop waits up to250ms for I/O and wakes on arrivals, without an extra sleep after every pump. Disconnected retries retain a positive wait. No parallel writer, contract, revision, identity, database schema or producer change. Commit-before-ACK and existing receipt/revision deduplication remain intact.

Added payload-free parse/write/ACK timing, redelivery flag and snapshot creation age. `snapshotAgeMs` includes upstream Outbox and recovery delay; it is not the same as publication-to-receipt latency.

Production-host isolated A/B on installed Pika1.3.2 and the same Aliyun endpoint, using independent random exclusive queues and simulated2ms commits: old10.02events/s, optimized83.98 and86.24events/s. Each run received120/120 unique matching messages; connections closed and exclusive queues cleaned up. No business queue consumed and no production database written by this probe. These figures isolate transport overhead and do not claim actual database throughput.

78 local synthetic tests passed, including partial prefetched-window write failure/recovery, committed-event redelivery, stale/duplicate handling, reconnect and commit-before-ACK. Production deployment and natural-message verification will be recorded below.

## Deployment and rollback

Before install, verify current hashes and sole active service; back up the exact installed consumer under restricted `config/deployments/snapshot-speed-20261021`. Gracefully stop it, atomically replace only the committed consumer, restart the same unit and verify ready/prefetch8/writers1, unchanged configuration and other modules. UnACKed deliveries remain recoverable. If verification fails, restore only the prior Aliyun-only consumer and restart one writer; never restore DRAIN/tunnel or legacy Respond writes. No purge, copy, replay, bootstrap or customer test send.

## Production result

Pending the scoped deployment and bounded receipt/revision checks. No performance result is asserted before those checks.
