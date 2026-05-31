#!/usr/bin/env python3
"""
Service TTS arabe — gTTS (Google TTS, gratuit, langue arabe).
Écoute sur http://127.0.0.1:5002.
POST texte UTF-8 → retourne WAV 8kHz mono.
GET / → health check.
"""

import os, tempfile, subprocess, logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from gtts import gTTS

logging.basicConfig(
    filename="/var/log/asterisk/edgetts_service.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)
log = logging.getLogger("tts_service")

log.info("Service TTS arabe (gTTS) démarré")


class TTSHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            text = self.rfile.read(length).decode("utf-8")

            mp3_path = tempfile.mktemp(suffix=".mp3")
            wav_path = tempfile.mktemp(suffix=".wav")

            try:
                tts = gTTS(text=text, lang="ar", slow=False)
                tts.save(mp3_path)

                subprocess.run(
                    ["ffmpeg", "-y", "-i", mp3_path, wav_path],
                    capture_output=True, check=True
                )

                with open(wav_path, "rb") as f:
                    wav_data = f.read()

                log.info(f"TTS: {text!r} ({len(wav_data)} bytes)")
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(wav_data)))
                self.end_headers()
                self.wfile.write(wav_data)

            finally:
                for p in (mp3_path, wav_path):
                    try:
                        os.unlink(p)
                    except Exception:
                        pass

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
