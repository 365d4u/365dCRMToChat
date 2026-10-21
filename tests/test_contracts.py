import unittest

from crm_to_chat.contracts import MAX_EVENT_BYTES, decode_json, parse_event, projection
from crm_to_chat.errors import ContractError
from helpers import encoded, fixture


class ContractTests(unittest.TestCase):
    def test_bigint_ids_remain_strings_and_resources_use_crm_identity(self):
        event = parse_event(encoded(fixture(message_id="9223372036854775807")))
        value = projection(event)
        self.assertEqual(value["message"]["messageId"], "9223372036854775807")
        self.assertEqual(value["message"]["attachments"][0]["resourceId"], "message/9223372036854775807/0")
        self.assertEqual(value["identity"]["messageKey"], "crm:1:message:9223372036854775807")
        self.assertFalse(value["chatDbWriteSupported"])

    def test_reject_ambiguous_or_provider_specific_input(self):
        cases = []
        for key, value in (("messageId", 1001), ("messageId", "1٢"), ("messageId", "9223372036854775808"),
                           ("occurredAt", "2026-10-10T10:00:00"), ("deleted", 1)):
            data = fixture()
            data["message"][key] = value
            cases.append(data)
        data = fixture()
        data["message"]["rawMessage"] = {"secret": "fixture-only"}
        cases.append(data)
        data = fixture()
        data["message"]["attachments"][0]["index"] = 1
        cases.append(data)
        data = fixture()
        data["message"]["attachments"][0]["url"] = "https://expired.example.test"
        cases.append(data)
        data = fixture()
        data["schemaVersion"] = True
        cases.append(data)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ContractError):
                parse_event(encoded(value))

    def test_deleted_content_is_rejected_and_unlinked_customer_has_no_wrong_jump(self):
        data = fixture()
        data["message"]["deleted"] = True
        with self.assertRaises(ContractError):
            parse_event(encoded(data))
        data["message"].update(text=None, attachments=[], customerId=None)
        self.assertIsNone(projection(parse_event(encoded(data)))["crmUrl"])

    def test_duplicate_keys_nonfinite_and_oversize_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'\xff', b"x" * (MAX_EVENT_BYTES + 1)):
            with self.subTest(raw=raw[:20]), self.assertRaises(ContractError):
                decode_json(raw)
