"""
streamdeck_api.py — Serveur HTTP local pour l'integration StreamDeck.

Permet au plugin Elgato StreamDeck de controler MyStrow via HTTP REST
sur http://127.0.0.1:8765/api/...

Endpoints:
  GET  /api/state                    → etat complet (JSON)
  POST /api/play                     → toggle play/pause
  POST /api/next                     → media suivant
  POST /api/prev                     → media precedent
  POST /api/blackout                 → full blackout toggle
  POST /api/level/{fader_idx}/{val}  → niveau fader 0-8, valeur 0-100
  POST /api/effect/{idx}             → toggle effet 0-7
  POST /api/mute/{fader_idx}/{0|1}   → mute/unmute fader
"""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from PySide6.QtCore import QObject, Signal

# Port d'ecoute du serveur HTTP local
STREAMDECK_API_PORT = 8765


# ---------------------------------------------------------------------------
# Bridge Qt — assure que les appels arrivent dans le thread principal Qt
# ---------------------------------------------------------------------------

class _StreamDeckBridge(QObject):
    """Signaux Qt : emis depuis le thread HTTP, traites dans le thread Qt."""

    play_requested     = Signal()
    next_requested     = Signal()
    prev_requested     = Signal()
    blackout_requested = Signal()
    level_requested    = Signal(int, int)   # (fader_idx, value 0-100)
    effect_requested   = Signal(int)        # effect_idx 0-7
    mute_requested     = Signal(int, bool)  # (fader_idx, active)


# ---------------------------------------------------------------------------
# Handler HTTP
# ---------------------------------------------------------------------------

def _make_handler(bridge: _StreamDeckBridge, window_ref: list):
    """Fabrique le handler HTTP avec acces au bridge et a la fenetre."""

    class _Handler(BaseHTTPRequestHandler):

        def log_message(self, fmt, *args):  # silence les logs HTTP
            pass

        # ── helpers ────────────────────────────────────────────────────────

        def _send_json(self, data, status=200):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def _send_error(self, msg, status=400):
            self._send_json({"error": msg}, status)

        def _parts(self):
            return [p for p in urlparse(self.path).path.split("/") if p]

        # ── CORS pre-flight ─────────────────────────────────────────────────

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        # ── GET /api/state ──────────────────────────────────────────────────

        def do_GET(self):
            parts = self._parts()
            if parts == ["api", "state"]:
                self._handle_state()
            else:
                self._send_error("Not found", 404)

        def _handle_state(self):
            w = window_ref[0]
            if w is None:
                self._send_json({"error": "not ready"}, 503)
                return
            try:
                from PySide6.QtMultimedia import QMediaPlayer

                is_playing = w.player.playbackState() == QMediaPlayer.PlayingState

                # Media courant
                current_row  = getattr(w.seq, "current_row", -1)
                current_media = ""
                if current_row >= 0:
                    item = w.seq.table.item(current_row, 1)
                    current_media = item.text() if item else ""

                # Niveaux faders (sliders Qt)
                fader_levels = [
                    w.faders[i].value()
                    for i in sorted(w.faders.keys())
                    if i in w.faders
                ]

                # Effets
                active_effects = [
                    {
                        "index": i,
                        "name": btn.current_effect or "",
                        "active": bool(btn.active),
                    }
                    for i, btn in enumerate(w.effect_buttons)
                ]

                # Projecteurs
                projectors = [
                    {
                        "name":   p.name,
                        "group":  p.group,
                        "level":  p.level,
                        "color":  p.color.name(),
                        "muted":  p.muted,
                    }
                    for p in w.projectors
                ]

                self._send_json({
                    "playing":       is_playing,
                    "pause_mode":    w.pause_mode,
                    "current_media": current_media,
                    "current_row":   current_row,
                    "fader_levels":  fader_levels,
                    "active_effects": active_effects,
                    "projectors":    projectors,
                })
            except Exception as exc:
                self._send_json({"error": str(exc)}, 500)

        # ── POST /api/* ──────────────────────────────────────────────────────

        def do_POST(self):
            parts = self._parts()

            if len(parts) < 2 or parts[0] != "api":
                self._send_error("Not found", 404)
                return

            action = parts[1]

            if action == "play":
                bridge.play_requested.emit()
                self._send_json({"ok": True})

            elif action == "next":
                bridge.next_requested.emit()
                self._send_json({"ok": True})

            elif action == "prev":
                bridge.prev_requested.emit()
                self._send_json({"ok": True})

            elif action == "blackout":
                bridge.blackout_requested.emit()
                self._send_json({"ok": True})

            elif action == "level":
                # POST /api/level/{fader_idx 0-8}/{value 0-100}
                try:
                    idx = int(parts[2])
                    val = int(parts[3])
                    if not (0 <= idx <= 8):
                        raise ValueError("fader_idx hors plage 0-8")
                    if not (0 <= val <= 100):
                        raise ValueError("value hors plage 0-100")
                    bridge.level_requested.emit(idx, val)
                    self._send_json({"ok": True})
                except (IndexError, ValueError) as exc:
                    self._send_error(f"Usage: /api/level/{{0-8}}/{{0-100}} — {exc}")

            elif action == "effect":
                # POST /api/effect/{idx 0-7}
                try:
                    idx = int(parts[2])
                    if not (0 <= idx <= 7):
                        raise ValueError("idx hors plage 0-7")
                    bridge.effect_requested.emit(idx)
                    self._send_json({"ok": True})
                except (IndexError, ValueError) as exc:
                    self._send_error(f"Usage: /api/effect/{{0-7}} — {exc}")

            elif action == "mute":
                # POST /api/mute/{fader_idx 0-7}/{0|1}
                try:
                    idx    = int(parts[2])
                    active = bool(int(parts[3]))
                    if not (0 <= idx <= 7):
                        raise ValueError("fader_idx hors plage 0-7")
                    bridge.mute_requested.emit(idx, active)
                    self._send_json({"ok": True})
                except (IndexError, ValueError) as exc:
                    self._send_error(f"Usage: /api/mute/{{0-7}}/{{0|1}} — {exc}")

            else:
                self._send_error(f"Action inconnue : {action}", 404)

    return _Handler


# ---------------------------------------------------------------------------
# Classe principale — instanciee par MainWindow
# ---------------------------------------------------------------------------

class StreamDeckAPIServer:
    """
    Serveur HTTP local pour le plugin StreamDeck.

    Usage dans MainWindow.__init__ :
        self._streamdeck_server = StreamDeckAPIServer(self)
        self._streamdeck_server.start()

    Usage dans MainWindow.closeEvent :
        self._streamdeck_server.stop()
    """

    def __init__(self, window):
        self._window_ref = [window]
        self._bridge     = _StreamDeckBridge(window)  # parent Qt pour la duree de vie
        self._server     = None
        self._thread     = None
        self._port       = STREAMDECK_API_PORT
        self._connect_signals(window)

    # ── connexion signaux → slots MainWindow ────────────────────────────────

    def _connect_signals(self, window):
        b = self._bridge
        b.play_requested.connect(window.toggle_play)
        b.next_requested.connect(window.next_media)
        b.prev_requested.connect(window.previous_media)
        b.blackout_requested.connect(window.full_blackout)
        b.level_requested.connect(window.set_proj_level)
        b.effect_requested.connect(window.toggle_effect)
        b.mute_requested.connect(window.toggle_mute)

    # ── cycle de vie ────────────────────────────────────────────────────────

    def start(self, port: int = STREAMDECK_API_PORT) -> bool:
        self._port = port
        handler = _make_handler(self._bridge, self._window_ref)
        try:
            self._server = HTTPServer(("127.0.0.1", port), handler)
        except OSError as exc:
            print(f"[StreamDeck API] Impossible de demarrer sur le port {port} : {exc}")
            return False

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="streamdeck-api",
        )
        self._thread.start()
        print(f"[StreamDeck API] Serveur demarre — http://127.0.0.1:{port}/api/")
        return True

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None
            print("[StreamDeck API] Serveur arrete")
