#!/usr/bin/env python3
"""
Restaurant AGI — Asterisk Gateway Interface
Flux : Asterisk → AGI → Whisper STT → Mistral AI → gTTS → Asterisk
"""

import sys
import os
import io
import json
import uuid
import signal
import time
import logging
import subprocess
import tempfile
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

MISTRAL_API_KEY  = os.environ.get("MISTRAL_API_KEY", "")
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
AGENT_API_URL    = os.environ.get("AGENT_API_URL", "http://agent:8000")
WHISPER_SERVICE  = "http://127.0.0.1:5001/"
PIPER_SERVICE    = "http://127.0.0.1:5002/"
SOUNDS_DIR       = Path("/var/lib/asterisk/sounds")
MENU_PATH        = Path("/var/lib/asterisk/agi-bin/menu.json")

logging.basicConfig(
    filename="/var/log/asterisk/restaurant_agi.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)
log = logging.getLogger("restaurant_agi")

# ──────────────────────────────────────────────────────────────────────────────
# AGI layer
# ──────────────────────────────────────────────────────────────────────────────

class HangupError(Exception):
    pass

class AGI:
    def __init__(self):
        self.env = {}
        self._stdin  = sys.stdin
        self._stdout = sys.stdout
        self._read_env()

    def _read_env(self):
        while True:
            line = self._stdin.readline()
            if not line or line.strip() == "":
                break
            if ":" in line:
                k, v = line.split(":", 1)
                self.env[k.strip()] = v.strip()

    def _exec(self, cmd: str) -> str:
        try:
            self._stdout.write(cmd + "\n")
            self._stdout.flush()
        except (BrokenPipeError, OSError):
            raise HangupError("Canal raccroché (écriture)")
        line = self._stdin.readline()
        if not line:
            raise HangupError("Canal raccroché (EOF)")
        return line.strip()

    def _result(self, resp: str) -> int:
        try:
            return int(resp.split("result=")[1].split()[0].strip("()"))
        except Exception:
            return -1

    def answer(self):
        self._exec("ANSWER")

    def hangup(self):
        try:
            self._exec("HANGUP")
        except Exception:
            pass

    def stream_file(self, path: str, escape: str = "0123456789#*") -> int:
        return self._result(self._exec(f'STREAM FILE "{path}" "{escape}"'))

    def record_file(self, path: str, fmt: str = "wav",
                    escape: str = "#", timeout_ms: int = 15000,
                    silence_s: int = 1) -> bool:
        resp = self._exec(
            f'RECORD FILE "{path}" {fmt} "{escape}" {timeout_ms} 0 beep s={silence_s}'
        )
        return self._result(resp) >= 0

    def verbose(self, msg: str, level: int = 1):
        try:
            self._exec(f'VERBOSE "{msg}" {level}')
        except HangupError:
            raise
        except Exception:
            pass

    @property
    def caller_id(self) -> str:
        return self.env.get("agi_callerid", "unknown")

    @property
    def unique_id(self) -> str:
        return self.env.get("agi_uniqueid", str(uuid.uuid4()))


# ──────────────────────────────────────────────────────────────────────────────
# Menu
# ──────────────────────────────────────────────────────────────────────────────

def load_menu() -> dict:
    try:
        with open(MENU_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Impossible de charger menu.json: {e}")
        return {"restaurant": {}, "menu": {}}

MENU_DATA = load_menu()

def build_menu_text() -> str:
    return "\n".join(
        f"  - {item['nom']} [{key}] : {item['prix']} TND"
        for key, item in MENU_DATA.get("menu", {}).items()
    )

# ──────────────────────────────────────────────────────────────────────────────
# STT — service Whisper persistant (HTTP)
# ──────────────────────────────────────────────────────────────────────────────

def transcribe(audio_path: str) -> str:
    wav16k = audio_path.replace(".wav", "_16k.wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", wav16k],
            capture_output=True, check=True
        )
        with open(wav16k, "rb") as f:
            data = f.read()

        # Appelle le service Whisper persistant (3 tentatives max)
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    WHISPER_SERVICE, data=data,
                    headers={"Content-Type": "audio/wav"}
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    result = json.loads(resp.read())
                text = result.get("text", "")
                log.info(f"STT: {text!r}")
                return text
            except urllib.error.URLError as e:
                log.warning(f"Whisper service attempt {attempt+1}: {e}")
                if attempt < 2:
                    time.sleep(3)

        log.error("Whisper service indisponible")
        return ""
    except Exception as e:
        log.error(f"Erreur STT: {e}")
        return ""
    finally:
        try:
            os.unlink(wav16k)
        except Exception:
            pass

# ──────────────────────────────────────────────────────────────────────────────
# TTS — gTTS → WAV 8 kHz pour Asterisk
# ──────────────────────────────────────────────────────────────────────────────

def text_to_wav(text: str, out_path: str) -> bool:
    """TTS via service Piper (voix féminine naturelle). Fallback espeak-ng."""
    piper_wav = out_path + ".piper.wav"
    try:
        req = urllib.request.Request(
            PIPER_SERVICE,
            data=text.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            wav_data = resp.read()
        with open(piper_wav, "wb") as f:
            f.write(wav_data)
        subprocess.run(
            ["ffmpeg", "-y", "-i", piper_wav,
             "-ar", "8000", "-ac", "1", "-acodec", "pcm_s16le", out_path],
            capture_output=True, check=True
        )
        return True
    except Exception as e:
        log.warning(f"Piper indisponible ({e}), fallback espeak")
        try:
            tmp = out_path + ".esp.wav"
            r = subprocess.run(
                ["espeak-ng", "-v", "fr", "-s", "140", "--stdout", text],
                capture_output=True, check=True
            )
            with open(tmp, "wb") as f:
                f.write(r.stdout)
            subprocess.run(
                ["ffmpeg", "-y", "-i", tmp,
                 "-ar", "8000", "-ac", "1", "-acodec", "pcm_s16le", out_path],
                capture_output=True, check=True
            )
            os.unlink(tmp)
            return True
        except Exception as e2:
            log.error(f"Erreur TTS fallback: {e2}")
            return False
    finally:
        try:
            os.unlink(piper_wav)
        except Exception:
            pass

def say(agi: AGI, text: str, wav_path: str) -> int:
    """Génère le TTS et le joue. wav_path sans extension."""
    if text_to_wav(text, wav_path + ".wav"):
        return agi.stream_file(wav_path)
    return -1

def play_static(agi: AGI, key: str, fallback_text: str, tmpdir: Path) -> int:
    """Joue un fichier pré-généré au démarrage, ou génère à la volée."""
    static = SOUNDS_DIR / key
    if (static.parent / (static.name + ".wav")).exists():
        return agi.stream_file(str(static))
    return say(agi, fallback_text, str(tmpdir / key))

# ──────────────────────────────────────────────────────────────────────────────
# Mistral AI
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es un agent vocal IA pour le restaurant "{name}". Tu parles uniquement en FRANÇAIS.

Menu disponible:
{menu}

PROTOCOLE (respecte cet ordre):
1. Prends la commande (écoute produits et quantités)
2. Répète les articles commandés pour confirmation
3. Demande: "Livraison à domicile ou sur place?"
4. Si livraison: demande nom → téléphone → adresse (une info à la fois)
5. Si sur place: demande juste le prénom
6. Récapitule la commande, donne le total et annonce "délai estimé: 20 minutes"
7. Attends la confirmation du client ("oui", "c'est bon", etc.)
8. Dis: "Merci et à très bientôt!" puis clôture (action=order_complete)

RÈGLES:
- Phrases courtes et naturelles (style téléphonique)
- Ne demande qu'une seule information à la fois
- Si tu ne comprends pas, demande poliment de répéter
- Total = somme des prix × quantités

FORMAT JSON OBLIGATOIRE (rien en dehors du JSON):
{{"action":"continue","response_text":"...","order":{{"items":[{{"product_key":"...","product_name":"...","quantity":1,"unit_price":0}}],"delivery_type":"livraison|sur_place|","customer_name":"","customer_phone":"","address":"","total":0}}}}

action="order_complete" UNIQUEMENT après confirmation explicite du client.
"""

class MistralConversation:
    def __init__(self):
        from mistralai import Mistral
        self.client = Mistral(api_key=MISTRAL_API_KEY)
        restaurant = MENU_DATA.get("restaurant", {})
        self.system = SYSTEM_PROMPT.format(
            name=restaurant.get("nom", "Restaurant"),
            menu=build_menu_text()
        )
        self.history = []
        self.order = {
            "items": [], "delivery_type": "",
            "customer_name": "", "customer_phone": "",
            "address": "", "total": 0.0
        }

    def send(self, user_text: str) -> dict:
        self.history.append({"role": "user", "content": user_text})
        if len(self.history) > 20:
            self.history = self.history[-20:]

        last_err = None
        for attempt in range(4):
            if attempt > 0:
                wait = 2 ** attempt
                log.info(f"Retry Mistral {attempt}/3 après {wait}s...")
                time.sleep(wait)
            try:
                resp = self.client.chat.complete(
                    model="mistral-small-latest",
                    messages=[{"role": "system", "content": self.system}, *self.history],
                    response_format={"type": "json_object"},
                    max_tokens=400,
                    temperature=0.3
                )
                raw = resp.choices[0].message.content
                self.history.append({"role": "assistant", "content": raw})
                result = json.loads(raw)
                self._merge_order(result.get("order", {}))
                result["order"] = self.order
                return result
            except json.JSONDecodeError:
                return {"action": "continue",
                        "response_text": "Pouvez-vous répéter s'il vous plaît?",
                        "order": self.order}
            except Exception as e:
                last_err = e
                if "429" in str(e) or "capacity" in str(e).lower():
                    log.warning(f"Mistral 429 attempt {attempt}: {e}")
                    continue
                log.error(f"Mistral error: {e}")
                break

        log.error(f"Mistral échec après 4 tentatives: {last_err}")
        return {"action": "continue",
                "response_text": "Désolé, un problème technique. Pouvez-vous répéter?",
                "order": self.order}

    def _merge_order(self, new: dict):
        if not new:
            return
        if new.get("items"):
            self.order["items"] = new["items"]
        for f in ("delivery_type", "customer_name", "customer_phone", "address"):
            if new.get(f):
                self.order[f] = new[f]
        self.order["total"] = round(
            sum(i.get("unit_price", 0) * i.get("quantity", 1) for i in self.order["items"]), 3
        )

# ──────────────────────────────────────────────────────────────────────────────
# Telegram + API
# ──────────────────────────────────────────────────────────────────────────────

def send_telegram(order: dict, call_id: str):
    try:
        import httpx
        items = order.get("items", [])
        lines = "".join(
            f"  • {i.get('quantity',1)}x {i.get('product_name','?')} — "
            f"{i.get('unit_price',0)*i.get('quantity',1)} TND\n"
            for i in items
        )
        mode = "🚗 Livraison" if order.get("delivery_type") == "livraison" else "🏪 Sur place"
        addr = f"\n📍 *Adresse:*\n{order['address']}" if order.get("address") else ""
        ref  = call_id[-8:].upper()
        msg = (
            f"📦 *Nouvelle Commande* — `{ref}`\n\n"
            f"👤 *Client:* {order.get('customer_name') or 'N/A'}\n"
            f"📞 *Téléphone:* {order.get('customer_phone') or 'N/A'}\n\n"
            f"🍽️ *Produits:*\n{lines}\n"
            f"💰 *Total:* {order.get('total',0)} TND\n\n"
            f"{mode}{addr}\n\n🕒 *Heure:* {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        with httpx.Client(timeout=10) as client:
            client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
            )
        log.info("Telegram envoyé.")
    except Exception as e:
        log.error(f"Telegram error: {e}")

def save_order_via_api(order: dict, call_sid: str, caller_id: str):
    try:
        import httpx
        with httpx.Client(timeout=10) as client:
            client.post(
                f"{AGENT_API_URL}/api/internal/order",
                json={"order": order, "call_sid": call_sid, "caller_id": caller_id}
            )
        log.info("Commande sauvegardée via API.")
    except Exception as e:
        log.error(f"Erreur sauvegarde API: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# Boucle principale AGI
# ──────────────────────────────────────────────────────────────────────────────

MAX_TURNS = 20

def main():
    signal.signal(signal.SIGPIPE, signal.SIG_IGN)

    agi       = AGI()
    call_id   = agi.unique_id
    caller_id = agi.caller_id

    log.info(f"=== Appel | uid={call_id} | from={caller_id} ===")

    tmpdir = Path(tempfile.mkdtemp(prefix=f"agi_{call_id}_"))

    try:
        agi.answer()

        conv = MistralConversation()
        restaurant = MENU_DATA.get("restaurant", {})
        name = restaurant.get("nom", "notre restaurant")

        play_static(agi, "restaurant_greeting",
                    f"Bonjour, {name}! Que souhaitez-vous commander?",
                    tmpdir)

        order_confirmed = False

        for turn in range(MAX_TURNS):
            rec_path = str(tmpdir / f"turn_{turn}")
            rec_wav  = rec_path + ".wav"

            agi.verbose(f"Enregistrement tour {turn}...")
            ok = agi.record_file(rec_path, fmt="wav", timeout_ms=15000, silence_s=2)

            if not ok or not Path(rec_wav).exists():
                log.info(f"Tour {turn}: fin d'appel ou silence prolongé")
                break

            user_text = transcribe(rec_wav)
            try:
                os.unlink(rec_wav)
            except Exception:
                pass

            if not user_text.strip():
                log.info("Silence — on réécoute")
                play_static(agi, "restaurant_silence",
                            "Je n'ai pas entendu. Pouvez-vous répéter s'il vous plaît?",
                            tmpdir)
                continue

            log.info(f"Tour {turn} client: {user_text!r}")
            agi.verbose(f"Client: {user_text}")

            result = conv.send(user_text)
            response_text = result.get("response_text", "Pouvez-vous répéter?")
            action = result.get("action", "continue")

            log.info(f"Tour {turn} agent: {response_text!r} | action={action}")
            say(agi, response_text, str(tmpdir / f"resp_{turn}"))

            if action == "order_complete":
                order_confirmed = True
                order = result.get("order", conv.order)
                log.info(f"Commande confirmée: {order}")
                send_telegram(order, call_id)
                save_order_via_api(order, call_id, caller_id)
                break

        if not order_confirmed:
            play_static(agi, "restaurant_timeout",
                        "Merci de votre appel. N'hésitez pas à rappeler. Au revoir!",
                        tmpdir)

    except HangupError:
        log.info(f"Appel {call_id} terminé par le client.")
    except Exception as e:
        log.exception(f"Erreur fatale AGI: {e}")
        try:
            play_static(agi, "restaurant_error",
                        "Un problème est survenu. Veuillez rappeler. Au revoir!",
                        tmpdir)
        except Exception:
            pass
    finally:
        for f in tmpdir.iterdir():
            try:
                f.unlink()
            except Exception:
                pass
        try:
            tmpdir.rmdir()
        except Exception:
            pass
        agi.hangup()
        log.info(f"=== Fin appel {call_id} ===")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, newline="\n", line_buffering=True)
    sys.stdin  = io.TextIOWrapper(sys.stdin.buffer)
    main()
