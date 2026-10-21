# 365dCRMToChat

Current user scope (2026-10-12): prepare and safely execute the CRM source
cutover. Site conversation IDs are crm_<CRM customerId>, not conversation IDs.
Preserve historical rows, manual labels/groups, #fw and legacy realtime forwarding.
Use project deployment skills and server runtime configuration for production
integration, including databases not registered in Biz (explicit user override).
Never retrieve or expose database credentials. Local tests remain synthetic.

Deployment target explicitly specified by the user: 107.150.104.4, SSH port
2208, user ubuntu, project root /data/365dCRMToChat. Use its independent venv
and units. The former message-site-host consumer and tunnel are disabled;
the message site's media client remains there. Never run two writers during
host migration. Reuse server-owned chat_db configuration without transferring
database credentials. SSH passwords stay in DPAPI, not code or documentation.

Keep CRM-owned message and attachment identities independent of Respond and
Provider IDs. Accept canonical snapshots only; do not parse Provider payloads.
The snapshot envelope in docs/event-contract.md is deployed. Keep revisions,
scope checks and transaction boundaries consistent with the canonical publisher.

Offline fixtures are the default. RabbitMQ observation may consume only its
own randomly named exclusive copy queue, never an existing business queue.
Media presentation returns JSON URLs; do not proxy media bytes or expose tokens.

Use local synthetic fixtures for tests. Do not connect tests to production.
Use Biz CLI for registered company resources; for unregistered resources, the
user explicitly authorized deployment skills and server runtime configuration.
Never retrieve, store or expose database credentials.
Enable writes and disable the legacy writer only after schema, queue, media,
rollback and source-to-target verification pass. Preview commands remain read-only.

Latest user policy: never re-enable respond_to_msgsite chat_db writes, including
rollback. Its database access is SELECT-only for #fw agent lookup. CRM customer
search also resolves verified historical Respond references; do not infer mapping
from equal numeric IDs or names. Latest user policy: prefer Go CRM(customerId),
and fall back to Go Respond(respondId) when no usable CRM mapping exists and the
legacy Respond identity is explicit and unambiguous. The fallback is navigation
only; never re-enable legacy chat_db writes.
Reference synchronization uses its dedicated oneshot service and timer, a
source-restricted forced-command SSH key, and CRM-owned verified references.
Only automatically-owned mapping rows may be refreshed or revoked. Preserve
manual mappings, old message tables, runtime configuration and recovery backups.
