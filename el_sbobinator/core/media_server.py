"""
Small local HTTP media streamer for the React audio player.
"""

from __future__ import annotations

import http.server
import mimetypes
import os
import re
import socketserver
import threading
import time
from typing import ClassVar


class LocalMediaServer:
    _servers: ClassVar[dict[str, tuple[socketserver.ThreadingTCPServer, int]]] = {}
    _lock: ClassVar[threading.Lock] = threading.Lock()
    MAX_ENTRIES = 5  # LRU cap to prevent port exhaustion

    @classmethod
    def _evict_oldest_if_needed(cls):
        """Shutdown and remove oldest server if over MAX_ENTRIES."""
        if len(cls._servers) < cls.MAX_ENTRIES:
            return
        # Pop oldest entry (dict preserves insertion order in Python 3.7+)
        oldest_path = next(iter(cls._servers))
        oldest_server, _ = cls._servers.pop(oldest_path)
        threading.Thread(
            target=lambda: (oldest_server.shutdown(), oldest_server.server_close()),
            daemon=True,
        ).start()

    @classmethod
    def stream_url_for_file(cls, file_path: str) -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError("File audio non trovato.")

        with cls._lock:
            if file_path in cls._servers:
                entry = cls._servers.pop(file_path)
                cls._servers[file_path] = entry
                _, port = entry
                return f"http://127.0.0.1:{port}/stream.media?t={time.time()}"

            served_path = file_path

            class MediaHandler(http.server.BaseHTTPRequestHandler):
                def end_headers(self):
                    self.send_header("Access-Control-Allow-Origin", "*")
                    super().end_headers()

                def do_GET(self):
                    if self.path.split("?", 1)[0] != "/stream.media":
                        self.send_error(404)
                        return
                    try:
                        path = served_path
                        if not os.path.exists(path):
                            self.send_error(404, "File not found")
                            return

                        size = os.path.getsize(path)
                        start, end = 0, size - 1
                        status_code = 200
                        range_header = self.headers.get("Range")
                        if range_header:
                            stripped = range_header.strip()
                            suffix_match = re.fullmatch(r"bytes=-(\d+)", stripped)
                            start_match = re.fullmatch(r"bytes=(\d+)-(\d*)", stripped)
                            if suffix_match:
                                suffix_len = int(suffix_match.group(1))
                                if suffix_len == 0 or size == 0:
                                    self.send_response(416)
                                    self.send_header("Content-Range", f"bytes */{size}")
                                    self.end_headers()
                                    return
                                start = max(0, size - suffix_len)
                                end = size - 1
                                status_code = 206
                            elif start_match:
                                start = int(start_match.group(1))
                                if start >= size:
                                    self.send_response(416)
                                    self.send_header("Content-Range", f"bytes */{size}")
                                    self.end_headers()
                                    return
                                if start_match.group(2):
                                    end = min(int(start_match.group(2)), size - 1)
                                else:
                                    end = size - 1
                                if end < start:
                                    self.send_response(416)
                                    self.send_header("Content-Range", f"bytes */{size}")
                                    self.end_headers()
                                    return
                                status_code = 206

                        length = end - start + 1
                        self.send_response(status_code)
                        ctype, _ = mimetypes.guess_type(path)
                        self.send_header("Content-Type", ctype or "audio/mpeg")
                        self.send_header("Accept-Ranges", "bytes")
                        self.send_header("Content-Length", str(length))
                        if status_code == 206:
                            self.send_header(
                                "Content-Range", f"bytes {start}-{end}/{size}"
                            )
                        self.end_headers()

                        with open(path, "rb") as handle:
                            handle.seek(start)
                            remaining = length
                            while remaining > 0:
                                chunk = handle.read(min(remaining, 65536))
                                if not chunk:
                                    break
                                self.wfile.write(chunk)
                                remaining -= len(chunk)
                    except Exception:
                        pass

                def log_message(self, format, *args):
                    pass

            cls._evict_oldest_if_needed()

            server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), MediaHandler)
            port = server.server_address[1]
            cls._servers[file_path] = (server, port)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{port}/stream.media?t={time.time()}"

    @classmethod
    def shutdown_all(cls):
        """Shutdown all servers. Called on app exit."""
        with cls._lock:
            for server, _ in cls._servers.values():
                try:
                    server.shutdown()
                    server.server_close()
                except Exception:
                    pass
            cls._servers.clear()
