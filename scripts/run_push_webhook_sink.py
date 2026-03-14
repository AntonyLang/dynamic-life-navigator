"""Run a tiny local webhook sink for push delivery smoke tests."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local webhook sink for push delivery smoke tests.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host. Defaults to 127.0.0.1.")
    parser.add_argument("--port", type=int, default=8787, help="Bind port. Defaults to 8787.")
    parser.add_argument(
        "--status-code",
        type=int,
        default=202,
        help="HTTP status code to return for every POST. Use 500 to simulate failure.",
    )
    parser.add_argument(
        "--output-jsonl",
        default="logs/push-webhook-sink.jsonl",
        help="Path to append received webhook events as JSONL.",
    )
    return parser.parse_args()


def make_handler(status_code: int, output_path: Path) -> type[BaseHTTPRequestHandler]:
    class PushWebhookHandler(BaseHTTPRequestHandler):
        server_version = "PushWebhookSink/1.0"

        def do_POST(self) -> None:  # noqa: N802
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            decoded_body = raw_body.decode("utf-8")

            try:
                payload: Any = json.loads(decoded_body)
            except json.JSONDecodeError:
                payload = {"raw_body": decoded_body}

            record = {
                "received_at": datetime.now(timezone.utc).isoformat(),
                "path": self.path,
                "headers": {key: value for key, value in self.headers.items()},
                "payload": payload,
            }
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")

            print(json.dumps(record, ensure_ascii=False, indent=2))

            response_body = json.dumps(
                {
                    "accepted": 200 <= status_code < 300,
                    "status_code": status_code,
                }
            ).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return PushWebhookHandler


def main() -> None:
    args = parse_args()
    output_path = Path(args.output_jsonl)
    handler = make_handler(args.status_code, output_path)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Push webhook sink listening on http://{args.host}:{args.port}")
    print(f"Writing received payloads to {output_path}")
    print(f"Responding with status code {args.status_code}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
