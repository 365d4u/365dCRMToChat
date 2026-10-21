from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from crm_to_chat.contracts import parse_event
from crm_to_chat.errors import IntegrationError
from crm_to_chat.preview import PreviewStore
from helpers import encoded, fixture


def event(**kwargs):
    return parse_event(encoded(fixture(**kwargs)))


class PreviewTests(unittest.TestCase):
    def test_duplicate_stale_and_delete_never_resurrect_content(self):
        with PreviewStore() as store:
            latest = event(event_id="new", revision="2")
            self.assertEqual(store.apply(latest), "applied")
            self.assertEqual(store.apply(latest), "duplicate")
            self.assertEqual(store.apply(event(event_id="old", revision="1")), "stale")
            data = fixture(event_id="delete", revision="3")
            data["message"].update(deleted=True, text=None, attachments=[])
            self.assertEqual(store.apply(parse_event(encoded(data))), "applied")
            self.assertEqual(store.apply(event(event_id="late-new", revision="2")), "stale")
            snapshot = store.snapshots()[0]
            self.assertTrue(snapshot["message"]["deleted"])
            self.assertIsNone(snapshot["message"]["text"])
            self.assertEqual(snapshot["message"]["attachments"], [])

    def test_conflicting_event_and_revision_roll_back_receipt(self):
        with PreviewStore() as store:
            store.apply(event())
            conflict = fixture()
            conflict["message"]["text"] = "different"
            with self.assertRaisesRegex(IntegrationError, "event_id_conflict"):
                store.apply(parse_event(encoded(conflict)))
            conflict["eventId"] = "other-event"
            with self.assertRaisesRegex(IntegrationError, "revision_conflict"):
                store.apply(parse_event(encoded(conflict)))
            self.assertEqual(store.connection.execute("SELECT COUNT(*) FROM preview_receipts").fetchone()[0], 1)
            conflict["revision"] = "2"
            self.assertEqual(store.apply(parse_event(encoded(conflict))), "applied")

    def test_workspace_namespace_and_local_restart(self):
        with TemporaryDirectory() as directory:
            state = str(Path(directory) / "preview.sqlite3")
            with PreviewStore(state) as store:
                store.apply(event())
                store.apply(event(workspace_id="2"))
            with PreviewStore(state) as store:
                self.assertEqual(store.apply(event()), "duplicate")
                self.assertEqual(len(store.snapshots()), 2)

    def test_existing_unrelated_sqlite_is_not_modified(self):
        with TemporaryDirectory() as directory:
            state = str(Path(directory) / "unrelated.sqlite3")
            with closing(sqlite3.connect(state)) as connection:
                connection.execute("CREATE TABLE user_data (value TEXT)")
                connection.commit()
            with self.assertRaisesRegex(IntegrationError, "unrecognized_preview_state"):
                PreviewStore(state)
            with closing(sqlite3.connect(state)) as connection:
                tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            self.assertEqual(tables, [("user_data",)])
