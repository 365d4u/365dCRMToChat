# Aliyun primary cutover — 2026-10-21

The user explicitly authorized production deployment, superseding preparation-only restrictions. Commit `0a41f0037e9f2a6cb6f5db0a66516b9971ca9a36` was pushed to origin/main before installation on 107.150.104.4:2208.

Stopped the sole consumer, backed up and installed only consume.py/rabbitmq.py/cli.py/observer.py, preserving writer/contracts/media.py, scope1, enabled writes, independent venv, server configuration and tunnel. Phase A consumed old primary plus Aliyun drain; phase B at 18:13 Beijing switched primary to Aliyun and old loopback source to drain. Final consumer PID3012763 active/NRestarts0, tunnel PID2194959 unchanged. No second writer, legacy Respond writes, migration, replay or customer test send.

The same serial transactional writer handles both sources; commit precedes source-specific ACK. Existing event receipts prevent repeated events; revision checks skip stale snapshots so older source deliveries cannot overwrite newer versions. Broker delivery remains at least once, not a physical exactly-once guarantee.

At 18:23:29 current-process outcomes were Aliyun applied5977/stale22 and old applied1473/stale167; no session/connection failure events. Old snapshot queue subsequently empty; Aliyun snapshot backlog still2325 at the sample and being consumed, not claimed caught up. Invalid queue0. Synthetic isolated real-host100-message probe passed confirms, TLS, mandatory returns, offline/unacked recovery, dead-letter retention, integrity and cleanup; p95 confirm16.05ms/delivery269.42ms. Local75 tests were synthetic.

Environment and original modules remain server-side in config/deployments/aliyun-cutover-20261021. Rollback retains two-source consumption and one writer; restore old primary while continuing Aliyun drain, never disable Aliyun consumer with pending snapshots. Old broker/tunnel/queues remain. No database credentials were retrieved or transferred.

Coordinated CRM deployment and limitations: `E:/PycharmProjects/365d_crm/docs/deployments/2026-10-21-aliyun-rabbitmq-cutover.md`. Instance16 deliveries/300s verified; history queue longer timeout edit did not save, guard had preexisting latched probe failure, one post-cutover event was quarantined for MESSAGE_IDENTITY_CONFLICT without replay. Branch cleanup follows main ancestry and exact-tip checks; independent no-remote preparation repository remains evidence.
