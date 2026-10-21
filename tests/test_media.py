import unittest
from http.client import IncompleteRead
from unittest.mock import patch
from urllib.error import HTTPError

from crm_to_chat.errors import ContractError, IntegrationError
from crm_to_chat.media import JsonTransport, MediaClient, NoRedirect, parse_media_request
from helpers import media_response


def resources(count):
    return parse_media_request({"resources": [{"resourceId": f"message/{index + 1}/0"} for index in range(count)]})


class MediaTests(unittest.TestCase):
    def test_chunk_deduplicate_and_restore_order(self):
        calls = []
        def transport(requests):
            calls.append(requests)
            return media_response(requests)
        request = resources(121)
        request += [request[0], request[60]]
        response = MediaClient(transport).resolve(request)
        self.assertEqual([len(group) for group in calls], [50, 50, 21])
        self.assertEqual(len(response["items"]), 123)
        self.assertEqual(response["items"][121], response["items"][0])
        self.assertEqual(response["items"][122], response["items"][60])

    def test_failed_batch_preserves_other_batches(self):
        calls = []
        def transport(requests):
            calls.append(requests)
            if len(calls) == 2:
                raise IntegrationError("crm_media_temporarily_unavailable")
            return media_response(requests)
        response = MediaClient(transport).resolve(resources(101))["items"]
        self.assertEqual(sum(item["status"] == "available" for item in response), 51)
        self.assertEqual(sum(item.get("retryable", False) for item in response), 50)
        self.assertEqual(response[100]["resourceId"], "message/101/0")

    def test_variants_exclusions_and_download_names_are_not_deduplicated_together(self):
        request = parse_media_request({"resources": [
            {"resourceId": "message/1/0", "variant": "preview"},
            {"resourceId": "message/1/0", "variant": "original", "excludedCandidates": ["source", "provider"]},
            {"resourceId": "message/1/0", "variant": "original", "downloadName": "movie.mp4"},
        ]})
        calls = []
        def transport(items):
            calls.extend(items)
            return media_response(items)
        MediaClient(transport).resolve(request)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[1]["excludedCandidates"], ["provider", "source"])
        self.assertEqual(calls[2]["downloadName"], "movie.mp4")

    def test_arbitrary_url_unknown_variant_and_oversize_input_rejected(self):
        for request in ({"resources": [{"resourceId": "https://internal.example.test"}]},
                        {"resources": [{"resourceId": "message/1/0", "variant": []}]},
                        {"resources": [{"resourceId": "message/1/0", "variant": "preview", "downloadName": "x"}]},
                        {"resources": [{"resourceId": "message/1/0"}] * 251}):
            with self.subTest(request=request), self.assertRaises(ContractError):
                parse_media_request(request)

    def test_mismatched_identity_and_credential_url_fail_closed(self):
        for mutate in (lambda response: response["items"][0].update(resourceId="message/999/0"),
                       lambda response: response["items"][0]["candidates"][0].update(url="https://user:secret@example.test/x")):
            def transport(requests):
                response = media_response(requests)
                mutate(response)
                return response
            item = MediaClient(transport).resolve(resources(1))["items"][0]
            self.assertEqual(item["status"], "unavailable")
            self.assertEqual(item["candidates"], [])
            self.assertNotIn("secret", str(item))

    def test_transport_never_follows_redirect_and_sanitizes_auth_error(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, None, None, None, None))
        transport = JsonTransport("https://crm.example.test", "synthetic-token")
        failure = HTTPError("https://crm.example.test/signed-secret", 401, "private details", {}, None)
        with patch.object(transport.opener, "open", side_effect=failure):
            with self.assertRaisesRegex(IntegrationError, "^crm_media_unauthorized$"):
                transport([{"resourceId": "message/1/0"}])

    def test_incomplete_http_response_is_a_retryable_batch_failure(self):
        transport = JsonTransport("https://crm.example.test", "synthetic-token")
        with patch.object(transport.opener, "open", side_effect=IncompleteRead(b"fixture-only", 100)):
            item = MediaClient(transport).resolve(resources(1))["items"][0]
        self.assertEqual(item["errorCode"], "crm_media_temporarily_unavailable")
        self.assertTrue(item["retryable"])
        self.assertNotIn("fixture-only", str(item))

    def test_no_token_no_network_and_origin_cannot_redirect_credentials(self):
        for base_url, token in (("https://crm.example.test", ""), ("http://crm.example.test", "token"),
                                ("https://crm.example.test/api", "token"),
                                ("https://user:secret@crm.example.test", "token")):
            with self.subTest(base_url=base_url), self.assertRaises(IntegrationError):
                JsonTransport(base_url, token)
