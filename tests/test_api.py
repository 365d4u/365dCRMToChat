from io import BytesIO
import json
import unittest

from crm_to_chat.api import MediaApi
from crm_to_chat.media import MediaClient
from helpers import encoded, media_response

TOKEN = "synthetic-service-token-32-characters-long"


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def transport(requests):
            self.calls.append(requests)
            return media_response(requests)
        self.app = MediaApi(MediaClient(transport), TOKEN)

    def request(self, value=None, *, path="/api/media/resolve", method="POST", auth=TOKEN,
                content_type="application/json", raw=None, length=None):
        body = encoded(value) if raw is None else raw
        environment = {"REQUEST_METHOD": method, "PATH_INFO": path,
                       "HTTP_AUTHORIZATION": "Bearer " + auth, "CONTENT_TYPE": content_type,
                       "CONTENT_LENGTH": str(len(body)) if length is None else length, "wsgi.input": BytesIO(body)}
        result = {}
        response = self.app(environment, lambda status, headers: result.update(status=status, headers=dict(headers)))
        return result, json.loads(b"".join(response))

    def test_authenticated_batch_splits_and_preserves_response(self):
        request = {"resources": [{"resourceId": f"message/{index + 1}/0"} for index in range(51)]}
        status, value = self.request(request)
        self.assertEqual(status["status"], "200 OK")
        self.assertEqual(status["headers"]["Cache-Control"], "no-store")
        self.assertEqual([len(group) for group in self.calls], [50, 1])
        self.assertEqual(len(value["items"]), 51)

    def test_unauthorized_call_does_not_reach_crm(self):
        for auth in ("", "wrong", "中文"):
            result, value = self.request({"resources": []}, auth=auth)
            self.assertEqual(result["status"], "401 Unauthorized")
        self.assertEqual(self.calls, [])

    def test_outbound_source_is_a_valid_canonical_media_candidate(self):
        def transport(requests):
            result = media_response(requests)
            result['items'][0]['candidates'][0].update(kind='source', source='outbound')
            return result
        self.app = MediaApi(MediaClient(transport), TOKEN)
        status, value = self.request({'resources': [{'resourceId': 'message/1001/0'}]})
        self.assertEqual(status['status'], '200 OK')
        self.assertEqual(value['items'][0]['candidates'][0]['source'], 'outbound')

    def test_invalid_json_url_content_type_and_size(self):
        cases = [({"raw": b'{"resources": [], "resources": []}'}, "400 Bad Request"),
                 ({"value": {"resources": [{"resourceId": "https://internal.example.test"}]}}, "400 Bad Request"),
                 ({"content_type": "text/plain"}, "415 Unsupported Media Type"),
                 ({"length": "999999999"}, "413 Payload Too Large"),
                 ({"length": "100", "raw": b"{}"}, "400 Bad Request")]
        for args, expected in cases:
            with self.subTest(args=args):
                result, _ = self.request(**args)
                self.assertEqual(result["status"], expected)
        self.assertEqual(self.calls, [])

    def test_health_is_local_capability_report_and_media_get_disallowed(self):
        result, value = self.request(path="/health", method="GET", auth="")
        self.assertEqual(result["status"], "200 OK")
        self.assertFalse(value["chatDbWriteSupported"])
        result, _ = self.request(method="GET")
        self.assertEqual(result["status"], "405 Method Not Allowed")
        result, _ = self.request(path="/media/proxy")
        self.assertEqual(result["status"], "404 Not Found")
