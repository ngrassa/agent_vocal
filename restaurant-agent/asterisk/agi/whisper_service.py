#!/usr/bin/env python3
"""
Service Whisper persistant — le modèle reste en RAM entre les appels.
Écoute sur http://127.0.0.1:5001 (POST = transcription, GET = health).
"""

import os, json, tempfile, logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from faster_whisper import WhisperModel

logging.basicConfig(
    filename="/var/log/asterisk/whisper_service.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)
log = logging.getLogger("whisper_service")

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")

log.info(f"Chargement Whisper ({WHISPER_MODEL})...")
model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
log.info("Whisper chargé — service prêt sur :5001")


class STTHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self):
        result = {"text": "", "error": None}
        try:
            length = int(self.headers.get("Content-Length", 0))
            audio_data = self.rfile.read(length)

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_data)
                tmp = f.name

            try:
                segs, info = model.transcribe(
                    tmp, language="fr", beam_size=3, vad_filter=True,
                    initial_prompt="pizza margherita quatre saisons coca cola livraison sur place commande bonjour merci"
                )
                text = " ".join(s.text for s in segs).strip()
                log.info(f"STT: {text!r} (p={info.language_probability:.2f})")
                result["text"] = text
            finally:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
        except Exception as e:
            log.error(f"Erreur transcription: {e}")
            result["error"] = str(e)

        body = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 5001), STTHandler)
    log.info("Écoute sur http://127.0.0.1:5001")
    server.serve_forever()
