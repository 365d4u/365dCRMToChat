"""Backfill only missing, verified legacy conversation links in the message site."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from .environment import mysql_config
from .references import history_links, read_snapshot

STATE = Path('/data/365dCRMToChat/state/reference-sync')
LOCK = 'crm-reference-import-v1'


def fetch_references():
    # Use the existing source-scoped, read-only exporter. Do not reuse an old snapshot.
    with TemporaryDirectory(prefix='legacy-once-', dir=STATE) as temporary:
        snapshot = Path(temporary) / 'references.ndjson'
        with snapshot.open('wb') as output:
            result = subprocess.run([
                'ssh', '-p', '2209', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                '-o', f'UserKnownHostsFile={STATE / "known_hosts"}', '-o', 'ConnectTimeout=15',
                '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
                '-i', str(STATE / 'id_ed25519'), 'ubuntu@154.197.57.214', 'export-crm-references',
            ], stdout=output, stderr=subprocess.DEVNULL, timeout=240)
        if result.returncode:
            raise RuntimeError('verified_reference_export_failed')
        refs, _ = read_snapshot(snapshot)
    if not refs:
        raise RuntimeError('empty_reference_export')
    return refs


def plan_missing(cursor, refs):
    cursor.execute("""
        SELECT legacy.conversation_id
        FROM chatwoot_conversation_update AS legacy
        WHERE LEFT(legacy.conversation_id, 4) <> 'crm_'
          AND NOT EXISTS (
              SELECT 1 FROM crm_conversation_link AS existing
              WHERE existing.conversation_id = legacy.conversation_id
          )
    """)
    conversations = {str(row['conversation_id']) for row in cursor.fetchall()}
    if not conversations:
        return {}, {'eligibleLegacy': 0, 'conflictingHistory': 0, 'unverifiedHistory': 0}
    cursor.execute("""
        SELECT chatwoot_conv_id, respond_conv_id FROM map_conversation_respond
        UNION SELECT chatwoot_conv_id, respond_conv_id FROM respond_conv_map
    """)
    edges = [(str(row['chatwoot_conv_id']), str(row['respond_conv_id']))
             for row in cursor.fetchall() if str(row['chatwoot_conv_id']) in conversations]
    # Every explicit alias counts, even if the fresh export cannot verify it.
    edges.extend((conversation, conversation[3:]) for conversation in conversations
                 if conversation.startswith('rd_'))
    links, stats = history_links(refs, conversations, edges)
    return links, {'eligibleLegacy': len(conversations), **stats}


def insert_missing(connection, links):
    records = [(conversation, customer, evidence)
               for conversation, (customer, evidence) in sorted(links.items())]
    inserted = 0
    for offset in range(0, len(records), 500):
        connection.begin()
        try:
            with connection.cursor() as cursor:
                inserted += cursor.executemany("""
                    INSERT INTO crm_conversation_link
                        (conversation_id, crm_customer_id, verified, evidence)
                    VALUES (%s, %s, 1, %s)
                    ON DUPLICATE KEY UPDATE conversation_id = crm_conversation_link.conversation_id
                """, records[offset:offset + 500])
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return inserted


def main():
    import pymysql

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    connection = pymysql.connect(**mysql_config(os.environ), charset='utf8mb4',
                                 cursorclass=pymysql.cursors.DictCursor,
                                 connect_timeout=8, read_timeout=30, write_timeout=30)
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT GET_LOCK(%s, 5) AS acquired', (LOCK,))
            if cursor.fetchone()['acquired'] != 1:
                raise RuntimeError('reference_import_already_running')
        refs = fetch_references()
        with connection.cursor() as cursor:
            cursor.execute('START TRANSACTION READ ONLY')
            links, stats = plan_missing(cursor, refs)
        connection.rollback()
        count = insert_missing(connection, links) if args.apply else 0
        print(json.dumps({'event': 'crm_legacy_backfill', 'applied': args.apply,
                          'planned': len(links), 'inserted': count, **stats}), flush=True)
    finally:
        connection.close()


if __name__ == '__main__':
    main()
