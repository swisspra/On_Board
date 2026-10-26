"""Behavioral regression for the confined dashboard HTTP server.

Launches dashboard_live.py --serve --port=0 as a subprocess against a throwaway
project, reads the actual bound port from stdout, and drives real HTTP requests
over loopback. External file/directory/index symlinks must be denied for GET and
HEAD without leaking their contents, while ordinary board JSON, dashboard HTML
and in-root files keep working.
"""

from __future__ import annotations

import http.client
import json
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = REPO_ROOT / "dashboard_live.py"
MARKER = "OUTSIDE-SECRET-9f3a4c"

class DashboardServer:
    """Owns one dashboard subprocess end to end.

    Drains its stdout, reaps the process, and closes the stdout pipe. Every
    ending path -- success, startup failure, timeout, interrupt or an assertion
    error -- must call stop(), so the pipe and drain thread are released
    explicitly instead of being reaped by the garbage collector mid-run.
    """

    def __init__(self, project: Path):
        self.proc = subprocess.Popen(
            [sys.executable, "-u", str(DASHBOARD), str(project), "--serve", "--port=0"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.lines: "queue.Queue[str]" = queue.Queue()
        self.port = None
        self._reader = threading.Thread(target=self._drain, daemon=True)
        self._reader.start()
        self._finished = False

    def _drain(self):
        # Returns at EOF once the child exits; a concurrent close() can instead
        # surface as a closed-file error, which is also a clean exit.
        try:
            for line in self.proc.stdout:
                self.lines.put(line)
        except (OSError, ValueError):
            pass

    def wait_for_port(self, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                line = self.lines.get(timeout=max(0.0, deadline - time.time()))
            except queue.Empty:
                break
            match = re.search(r"on port (\d+)", line)
            if match:
                self.port = int(match.group(1))
                return self.port
        raise AssertionError("dashboard server did not report a bound port")

    def stop(self, timeout=10):
        """Interrupt the server, return its exit code, and release the pipe."""
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=timeout)
        else:
            self.proc.wait(timeout=timeout)
        self._finish()
        return self.proc.returncode

    def _finish(self):
        if self._finished:
            return
        self._finished = True
        # Let the drain thread read the buffered tail (e.g. "Server stopped.")
        # before the pipe is closed under it.
        self._reader.join(timeout=5)
        if self.proc.stdout is not None:
            try:
                self.proc.stdout.close()
            except OSError:
                pass
        self._reader.join(timeout=5)


def start_server(project: Path):
    """Launch the dashboard server on an ephemeral port; return a DashboardServer."""
    server = DashboardServer(project)
    try:
        server.wait_for_port()
    except BaseException:
        server.stop()
        raise
    return server


def request(port, path, method="GET"):
    """Return (status, body-bytes) for one loopback request."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request(method, path)
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()

@pytest.fixture
def board(tmp_path):
    """Throwaway project whose board mirrors the audited symlink layout."""
    project = tmp_path / "proj"
    mem = project / ".agent-mem"
    mem.mkdir(parents=True)

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text(MARKER + "-dir", encoding="utf-8")
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text(MARKER, encoding="utf-8")

    (mem / "memory.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    sub = mem / "sub"
    sub.mkdir()
    (sub / "real.txt").write_text("INSIDE-OK", encoding="utf-8")

    (mem / "outside-link.txt").symlink_to(outside_file)
    (mem / "extdir").symlink_to(outside_dir, target_is_directory=True)
    (sub / "index.html").symlink_to(outside_file)

    server = start_server(project)
    try:
        yield {"port": server.port}
    finally:
        server.stop()

def test_ordinary_board_files_still_served(board):
    port = board["port"]

    status, body = request(port, "/dashboard-live.html")
    assert status == 200
    assert b"proj" in body

    status, body = request(port, "/memory.json")
    assert status == 200
    assert json.loads(body) == {"ok": True}

    status, body = request(port, "/sub/real.txt")
    assert status == 200
    assert b"INSIDE-OK" in body

    status, body = request(port, "/memory.json?cache=1")
    assert status == 200
    assert json.loads(body) == {"ok": True}

def test_external_file_symlink_denied_for_get_and_head(board):
    port = board["port"]

    status, body = request(port, "/outside-link.txt")
    assert status == 403
    assert MARKER.encode() not in body

    status, body = request(port, "/outside-link.txt", method="HEAD")
    assert status == 403
    assert MARKER.encode() not in body

def test_external_directory_symlink_denied(board):
    port = board["port"]

    status, body = request(port, "/extdir/secret.txt")
    assert status == 403
    assert MARKER.encode() not in body

    status, body = request(port, "/extdir/")
    assert status == 403
    assert MARKER.encode() not in body

    status, body = request(port, "/extdir/secret.txt", method="HEAD")
    assert status == 403
    assert MARKER.encode() not in body

def test_index_symlink_denied(board):
    port = board["port"]

    # Directory precheck alone passes here: "sub" is a real in-root directory.
    # Its index.html symlink escapes the root and must still be refused.
    status, body = request(port, "/sub/")
    assert status == 403
    assert MARKER.encode() not in body

    status, body = request(port, "/sub/index.html")
    assert status == 403
    assert MARKER.encode() not in body

def test_directory_listing_names_without_leaking_escapees(board):
    port = board["port"]

    status, body = request(port, "/")
    assert status == 200
    assert b"outside-link.txt" in body
    assert b"memory.json" in body
    assert MARKER.encode() not in body

    status, body = request(port, "/%2e%2e/outside.txt")
    assert status in (403, 404)
    assert MARKER.encode() not in body

def test_server_stops_cleanly_on_interrupt(tmp_path):
    project = tmp_path / "proj"
    mem = project / ".agent-mem"
    mem.mkdir(parents=True)
    (mem / "memory.json").write_text("{}", encoding="utf-8")

    server = start_server(project)
    try:
        assert request(server.port, "/memory.json")[0] == 200

        assert server.stop() == 0

        drained = ""
        deadline = time.time() + 5
        while time.time() < deadline and "Server stopped." not in drained:
            try:
                drained += server.lines.get(timeout=0.2)
            except queue.Empty:
                pass
        assert "Server stopped." in drained
    finally:
        server.stop()
