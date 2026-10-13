"""Run StreamCap headless with the new web UI.

python serve.py              # http://127.0.0.1:6008
python serve.py --open       # also open it in the default browser
"""

import argparse
import multiprocessing
import os
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from app.api.control.server import create_app
from app.app_manager import execute_dir
from app.core.runtime.backend_services import BackendServices
from app.core.runtime.paths import prepend_user_bin_dirs
from app.utils.logger import logger

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 6008
LOOPBACK_HOSTS = ["127.0.0.1", "localhost", "::1", "[::1]"]
STATIC_DIR = Path(__file__).resolve().parent / "webui" / "dist"


def main() -> None:
    load_dotenv()
    prepend_user_bin_dirs()
    parser = argparse.ArgumentParser(description="StreamCap web UI")
    parser.add_argument("--host", default=os.getenv("WEBUI_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.getenv("WEBUI_PORT", DEFAULT_PORT)))
    parser.add_argument("--open", action="store_true", help="open the UI in the default browser")
    args = parser.parse_args()

    services = BackendServices.bootstrap(execute_dir)
    services.start_background_loop()
    if not STATIC_DIR.is_dir():
        logger.warning(f"Web UI not built ({STATIC_DIR} missing) — run `npm run build` in webui/. Serving API only.")

    loopback = args.host in LOOPBACK_HOSTS
    if not loopback:
        logger.warning(
            f"Web UI bound to {args.host}: it has NO authentication. Anyone who can reach this port can "
            "control recordings, delete files and set the post-recording script command."
        )
    app = create_app(
        services, STATIC_DIR, Path(execute_dir) / "cache" / "webui", allowed_hosts=LOOPBACK_HOSTS if loopback else None
    )
    url = f"http://{args.host}:{args.port}"
    logger.info(f"StreamCap web UI: {url}")
    if args.open:
        threading.Timer(1.2, webbrowser.open, args=(url,)).start()
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    finally:
        shutdown(services)


def shutdown(services: BackendServices, timeout: float = 10.0) -> None:
    """Let recorders finish their files (same sequence as the desktop close handler)."""
    services.recording_enabled = False
    procs = services.process_manager.ffmpeg_processes
    deadline = time.monotonic() + timeout
    while any(p.returncode is None for p in procs) and time.monotonic() < deadline:
        time.sleep(0.3)
    fut = services.run_coro(services.process_manager.cleanup())
    if fut is not None and hasattr(fut, "result"):
        try:
            fut.result(timeout=8)
        except Exception as exc:
            logger.warning(f"process cleanup failed: {exc}")
    services.stop_background_loop()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
