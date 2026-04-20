#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Desktop launcher for My Perfumery.

Finds a free TCP port, starts the Flask app on it in a background thread,
waits for it to respond, then opens a pywebview window pointed at it.
"""

import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

APP_TITLE = "My Perfumery"
HOST = "127.0.0.1"
PREFERRED_PORTS = range(8000, 8100)   # try these first, then fall back
READY_TIMEOUT_SEC = 30


def pick_free_port():
    """Return a TCP port that is currently free on 127.0.0.1.

    First tries the preferred range so the URL stays recognizable for users
    who bookmark it. If every preferred port is taken, lets the OS pick one.
    """
    for port in PREFERRED_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((HOST, port))
            except OSError:
                continue
            return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def start_flask(port):
    """Run the Flask app in the current thread. Blocks until shutdown."""
    # Ensure app.py picks up the frozen-mode branches via env vars.
    os.environ["MYPERFUMERY_PORT"] = str(port)
    os.environ["MYPERFUMERY_HOST"] = HOST
    os.environ["MYPERFUMERY_DEBUG"] = "0"

    # Import here so the env vars are set before app.py evaluates them.
    import app as perfumery_app

    perfumery_app.bootstrap()
    perfumery_app.app.run(
        host=HOST,
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


def wait_until_ready(port, timeout=READY_TIMEOUT_SEC):
    """Poll the server until it responds or timeout expires."""
    url = f"http://{HOST}:{port}/"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status < 500:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.2)
    return False


def main():
    port = pick_free_port()

    server_thread = threading.Thread(
        target=start_flask, args=(port,), daemon=True, name="flask-server"
    )
    server_thread.start()

    if not wait_until_ready(port):
        # Fall back to the system browser so the user at least sees an error page.
        import webbrowser
        webbrowser.open(f"http://{HOST}:{port}/")
        server_thread.join()
        return

    import webview
    webview.create_window(
        APP_TITLE,
        f"http://{HOST}:{port}/",
        width=1280,
        height=860,
        min_size=(1024, 700),
    )
    webview.start()  # blocks until the window is closed


if __name__ == "__main__":
    main()
    # Daemon thread will die with the process; explicit exit for clarity.
    sys.exit(0)
