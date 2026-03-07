import os
import socket
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

from main import app

HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
PORT = int(os.getenv("BACKEND_PORT", "8000"))


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def health_ok(host: str, port: int) -> bool:
    url = f"http://{host}:{port}/api/health"
    try:
        with urlopen(url, timeout=2) as response:
            return 200 <= response.status < 300
    except URLError:
        return False
    except Exception:
        return False


def hold_forever() -> None:
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    if is_port_open(HOST, PORT):
        if health_ok(HOST, PORT):
            print(f"Backend already running at http://{HOST}:{PORT}. Reusing existing process.")
            hold_forever()
            sys.exit(0)
        print(
            f"Port {PORT} is in use by another process. "
            "Stop that process or set BACKEND_PORT and update frontend proxy target."
        )
        sys.exit(1)

    uvicorn.run(app, host=HOST, port=PORT)
