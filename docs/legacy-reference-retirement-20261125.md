# Legacy conversation jobs retired on November 25, 2026

The production message-site compute host was updated from CRMToChat main commit
`df470c43ab0ca5f9c57bd66d656e685344efa605`. The recurring importer module,
service, recurring timer, canceled 09:00 timer and runtime copies of both unit
templates were removed from their live paths. Before-images are archived under
`/data/365dCRMToChat/config/retired-legacy-reference-20261125`. The three old
systemd units no longer load. The shared snapshot parser and ownership matcher
remain in place for the separate one-time backfill. No historical business rows,
mapping data, exporter credentials or queue configuration were changed.

The deployed one-time backfill checksum matched its previous value, and
systemd still showed a single run at November 25 12:00 Asia/Shanghai.
Backfill execution and results were pending at verification. The CRM queue
consumer stayed active with PID 1625820 and zero restarts. Seventy-eight
offline tests passed. The temporary replacement file is absent. No build, new
dependency tree or remote upload stage was created. Available bytes on the
application filesystem were 19,514,187,776 before and 19,514,130,432 after
archiving and verification.

The same host's Respondstat Instagram-contact collector was removed from the
`www-data` crontab. The prior 19:20 and 07:20 Asia/Shanghai entries belonged to
one Cron expression. All other Cron lines and spool owner, group and mode
matched the baseline. No other active Cron or systemd invocation of the same
script was found. Its protected crontab before-image is under
`/var/backups/respondstat-instagram-cron-retirement-20261125`. Respondstat and
the existing support-statistics gateway remain active.
