import json
import threading
import unittest
from urllib.request import Request, urlopen
from wsgiref.simple_server import make_server

from crm_to_chat.api import MediaApi
from crm_to_chat.cli import LocalServer, QuietHandler
from crm_to_chat.media import MediaClient
from helpers import encoded, media_response


class LocalHttpTests(unittest.TestCase):
    def test_loopback_http_with_fake_crm_transport(self):
        token = "synthetic-service-token-long-enough"
        calls = []
        def transport(requests):
            calls.append(requests)
            return media_response(requests)
        app = MediaApi(MediaClient(transport), token)
        with make_server("127.0.0.1", 0, app, server_class=LocalServer, handler_class=QuietHandler) as server:
            worker = threading.Thread(target=server.handle_request, daemon=True)
            worker.start()
            try:
                request = Request(f"http://127.0.0.1:{server.server_port}/api/media/resolve",
                    data=encoded({"resources": [{"resourceId": "message/1/0"}]}),
                    headers={"Content-Type": "application/json", "Authorization": "Bearer " + token})
                with urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    value = json.load(response)
                self.assertEqual(value["items"][0]["resourceId"], "message/1/0")
                self.assertEqual(len(calls), 1)
            finally:
                worker.join(timeout=5)
                self.assertFalse(worker.is_alive())
