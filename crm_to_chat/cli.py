import argparse
from collections import Counter
from contextlib import nullcontext
import json
import os
from pathlib import Path
import sys
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from .api import MediaApi
from .config import bridge_token, enforce_preview_only, media_client, observer_config
from .contracts import MAX_EVENT_BYTES, decode_json, parse_event
from .errors import IntegrationError
from .media import batches, parse_media_request
from .observer import connect, observe
from .preview import PreviewStore


def emit(value):
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def write_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Refuse overwriting previous previews or user files.
    with target.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def read_media(path):
    with Path(path).open("rb") as handle:
        return parse_media_request(decode_json(handle.read(262_145), 262_144))


def preview(args):
    counts = Counter()
    source = nullcontext(sys.stdin.buffer) if args.input == "-" else Path(args.input).open("rb")
    with source as handle, PreviewStore(args.state) as store:
        line = 0
        while body := handle.readline(MAX_EVENT_BYTES + 2):
            line += 1
            if len(body) > MAX_EVENT_BYTES:
                # Drain one oversized JSONL record without interpreting its tail as a new event.
                while not body.endswith(b"\n") and body:
                    body = handle.readline(MAX_EVENT_BYTES + 2)
                counts["rejected"] += 1
                emit({"line": line, "outcome": "rejected", "error": "payload_too_large"})
                continue
            if not body.strip():
                continue
            try:
                event = parse_event(body)
                outcome = store.apply(event)
            except IntegrationError as error:
                counts["rejected"] += 1
                emit({"line": line, "outcome": "rejected", "error": error.code})
                continue
            counts[outcome] += 1
            emit({"line": line, "eventId": event.event_id, "workspaceId": event.workspace_id,
                  "messageId": event.message_id, "revision": str(event.revision), "outcome": outcome})
        if args.output:
            write_json(args.output, {"mode": "preview", "chatDbWriteSupported": False,
                                     "items": store.snapshots()})
    emit({"mode": "preview", "chatDbWriteSupported": False, "summary": dict(counts)})
    return 2 if counts["rejected"] else 0


def positive_int(value):
    value = int(value)
    if not 1 <= value <= 100_000:
        raise argparse.ArgumentTypeError("Expected 1..100000")
    return value


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *_):
        pass


class LocalServer(WSGIServer):
    def get_request(self):
        socket, address = super().get_request()
        socket.settimeout(30)
        return socket, address


def parser():
    result = argparse.ArgumentParser(description="365dCRMToChat: preview-only; chat_db writes are unavailable")
    commands = result.add_subparsers(dest="command", required=True)
    command = commands.add_parser("preview", help="Validate local JSONL and project to local preview state")
    command.add_argument("--input", required=True, help="JSONL file, or - for stdin")
    command.add_argument("--state", default=":memory:", help="Optional local .sqlite3 preview file")
    command.add_argument("--output", help="Optional snapshot JSON; includes message content")
    command = commands.add_parser("media-plan", help="Build CRM batches without network calls")
    command.add_argument("--input", required=True)
    command.add_argument("--output", help="Save batches to a new file")
    command = commands.add_parser("resolve-media", help="Explicitly call CRM with a runtime-injected token")
    command.add_argument("--input", required=True)
    command.add_argument("--output", required=True, help="New local JSON file for URL results")
    command = commands.add_parser("observe", help="Observe future events on a new temporary copy queue")
    command.add_argument("--max-messages", type=positive_int, default=100)
    command.add_argument("--seconds", type=positive_int, default=60)
    command.add_argument("--state", default=":memory:")
    command = commands.add_parser("serve", help="Run authenticated media gateway on loopback only")
    command.add_argument("--port", type=int, default=8791)
    commands.add_parser("check", help="Report local capabilities without connecting to anything")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        enforce_preview_only()
        if args.command == "check":
            emit({"service": "365dCRMToChat", "mode": "preview", "chatDbWriteSupported": False,
                  "databaseDriver": None, "crmBatchSize": 50, "bridgeBatchSize": 250,
                  "networkCalls": False})
            return 0
        if args.command == "preview":
            return preview(args)
        if args.command == "media-plan":
            groups = batches(read_media(args.input))
            value = {"batches": [{"resources": [item.request() for item in group]} for group in groups]}
            if args.output:
                write_json(args.output, value)
            else:
                emit(value)
            return 0
        if args.command == "resolve-media":
            if Path(args.output).exists():
                raise IntegrationError("output_already_exists")
            value = media_client().resolve(read_media(args.input))
            write_json(args.output, value)
            emit({"mode": "preview", "resolvedItems": len(value["items"]), "chatDbWriteSupported": False})
            return 2 if any(item.get("errorCode") for item in value["items"]) else 0
        if args.command == "observe":
            amqp_url, exchange, routing_key = observer_config()
            with PreviewStore(args.state) as store:
                connection = connect(amqp_url, os.environ.get('CRM_TO_CHAT_AMQP_INSTANCE_ID', ''))
                try:
                    count = observe(connection, exchange, routing_key, store, emit,
                                    max_messages=args.max_messages, duration=args.seconds)
                finally:
                    if connection.is_open:
                        connection.close()
            emit({"mode": "preview", "observedCopies": count, "chatDbWriteSupported": False})
            return 0
        if args.command == "serve":
            if not 1 <= args.port <= 65535:
                raise IntegrationError("invalid_port")
            app = MediaApi(media_client(), bridge_token())
            with make_server("127.0.0.1", args.port, app,
                             server_class=LocalServer, handler_class=QuietHandler) as server:
                emit({"service": "365dCRMToChat", "listen": f"127.0.0.1:{args.port}",
                      "mode": "preview", "chatDbWriteSupported": False})
                server.serve_forever()
    except IntegrationError as error:
        emit({"error": error.code, "chatDbWriteSupported": False})
        return 2
    except KeyboardInterrupt:
        return 130
    except Exception:
        # Paths, URLs, broker exceptions and business text must not leak into logs.
        emit({"error": "operation_failed", "chatDbWriteSupported": False})
        return 2
    return 0
