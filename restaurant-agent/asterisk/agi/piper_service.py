#!/usr/bin/env python3
"""
Service piper-tts persistant — voix française féminine naturelle.
Le modèle ONNX reste en RAM. Écoute sur http://127.0.0.1:5002.
POST texte UTF-8 → retourne WAV PCM brut.
GET / → health check.
"""

import io, wave, logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from piper.voice import PiperVoice

PIPER_MODEL = "/opt/piper-voices/fr.onnx"

logging.basicConfig(
    filename="/var/log/asterisk/piper_service.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)
log = logging.getLogger("piper_service")

log.info("Chargement Piper TTS (fr_FR-upmc-medium)...")
voice = PiperVoice.load(PIPER_MODEL)
log.info("Piper prêt — service actif sur :5002")


class TTSHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            text = self.rfile.read(length).decode("utf-8")

            buf = io.BytesIO()
            with wave.open(buf, "w") as wav_file:
                voice.synthesize(text, wav_file)
            buf.seek(0)
            wav_data = buf.read()

            log.info(f"TTS: {text!r} ({len(wav_data)} bytes)")
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav_data)))
            self.end_headers()
            self.wfile.write(wav_data)
        except Exception as e:
            log.error(f"Erreur TTS: {e}")
            self.send_response(500)
            self.end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 5002), TTSHandler)
    log.info("Écoute sur http://127.0.0.1:5002")
    server.serve_forever()
