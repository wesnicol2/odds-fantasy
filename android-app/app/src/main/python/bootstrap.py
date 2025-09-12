import os
import threading
from wsgiref.simple_server import make_server, WSGIServer, WSGIRequestHandler
from socketserver import ThreadingMixIn


def start_server(host: str = "127.0.0.1", port: int = 8000, debug: bool = False, api_key: str = "", data_dir: str = ""):
    """Starts the refactored.api WSGI server in a background thread.

    Expects refactored/* modules and top-level config to be present in sys.path
    (packaged under app/src/main/python).
    """
    # Configure environment for the backend
    if api_key:
        os.environ["API_KEY"] = api_key
    if data_dir:
        os.environ["DATA_DIR"] = data_dir
    os.environ.setdefault("SERVICE_CACHE_TTL", "120")
    os.environ.setdefault("ODDS_TTL", "43200")
    if debug:
        os.environ["API_DEBUG"] = "1"

    # Import after env setup
    from refactored.api import application, set_debug

    class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True
        allow_reuse_address = True

    class DebugRequestHandler(WSGIRequestHandler):
        def log_message(self, format, *args):  # noqa: A003
            if debug:
                try:
                    msg = format % args
                except Exception:
                    msg = str(format)
                reqline = getattr(self, 'requestline', '-')
                try:
                    peer = self.address_string()
                except Exception:
                    peer = '-'
                print(f"[api] {peer} \"{reqline}\" {msg}", flush=True)

    def _run():
        try:
            set_debug(debug)
        except Exception:
            pass
        try:
            httpd = make_server(host, port, application, server_class=ThreadingWSGIServer, handler_class=DebugRequestHandler)
        except OSError as e:
            print(f"[api] failed to bind {host}:{port}: {e}")
            return
        print(f"[api] Serving (embedded) on http://{host}:{port}")
        httpd.serve_forever()

    t = threading.Thread(target=_run, name="EmbeddedApiServer", daemon=True)
    t.start()
    return True

