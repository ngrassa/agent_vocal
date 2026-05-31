#!/bin/bash
# Génère les configs Asterisk depuis les variables d'environnement

set -e

SIP_HOST="${SIP_TRUNK_HOST:-}"
SIP_USER="${SIP_TRUNK_USER:-}"
SIP_PASS="${SIP_TRUNK_PASS:-}"
SIP_EXTENSION="${SIP_EXTENSION:-1000}"
SIP_EXT_PASS="${SIP_EXTENSION_PASS:-tunisian2024}"
PUBLIC_IP="${PUBLIC_IP:-}"

# ── asterisk.conf ──────────────────────────────────────────────────
cat > /etc/asterisk/asterisk.conf <<EOF
[options]
verbose = 3
debug = 0
nocolor = yes
EOF

# ── pjsip.conf ────────────────────────────────────────────────────
cat > /etc/asterisk/pjsip.conf <<EOF
;=== Transport UDP ===
[transport-udp]
type=transport
protocol=udp
bind=0.0.0.0:5060
external_media_address=${PUBLIC_IP}
external_signaling_address=${PUBLIC_IP}
local_net=10.0.0.0/8
local_net=172.16.0.0/12
local_net=192.168.0.0/16

;=== Extension interne (Zoiper / MizuDroid) ===
[${SIP_EXTENSION}]
type=endpoint
context=restaurants
disallow=all
allow=ulaw
allow=alaw
allow=gsm
auth=auth_${SIP_EXTENSION}
aors=aor_${SIP_EXTENSION}
direct_media=no
identify_by=username
rtp_symmetric=yes
force_rport=yes
rewrite_contact=yes

[auth_${SIP_EXTENSION}]
type=auth
auth_type=userpass
username=${SIP_EXTENSION}
password=${SIP_EXT_PASS}

[aor_${SIP_EXTENSION}]
type=aor
max_contacts=10
remove_existing=yes
default_expiration=120
minimum_expiration=60
maximum_expiration=300
EOF

# ── SIP trunk (optionnel) ─────────────────────────────────────────
if [ -n "$SIP_HOST" ] && [ -n "$SIP_USER" ]; then
cat >> /etc/asterisk/pjsip.conf <<EOF

;=== SIP Trunk ITSP ===
[trunk-transport]
type=transport
protocol=udp
bind=0.0.0.0:5061

[itsp-endpoint]
type=endpoint
context=from-trunk
disallow=all
allow=ulaw
allow=alaw
outbound_auth=itsp-auth
aors=itsp-aor
direct_media=no

[itsp-auth]
type=auth
auth_type=userpass
username=${SIP_USER}
password=${SIP_PASS}

[itsp-aor]
type=aor
contact=sip:${SIP_HOST}

[itsp-identify]
type=identify
endpoint=itsp-endpoint
match=${SIP_HOST}

[itsp-registration]
type=registration
outbound_auth=itsp-auth
server_uri=sip:${SIP_HOST}
client_uri=sip:${SIP_USER}@${SIP_HOST}
retry_interval=60
EOF
fi

# ── extensions.conf ────────────────────────────────────────────────
cat > /etc/asterisk/extensions.conf <<EOF
[general]
static=yes
writeprotect=no

; Appels entrants depuis le trunk SIP
[from-trunk]
exten => s,1,NoOp(Appel entrant trunk)
 same => n,Answer()
 same => n,AGI(restaurant_agi.py)
 same => n,Hangup()

exten => _X.,1,NoOp(Appel entrant DID: \${EXTEN})
 same => n,Answer()
 same => n,AGI(restaurant_agi.py)
 same => n,Hangup()

; Extension interne (test MizuDroid : composer le 7000)
[restaurants]
exten => 7000,1,NoOp(Test agent restaurant tunisien)
 same => n,Answer()
 same => n,AGI(restaurant_agi.py)
 same => n,Hangup()

exten => _X.,1,NoOp(Appel interne)
 same => n,Answer()
 same => n,AGI(restaurant_agi.py)
 same => n,Hangup()
EOF

# ── modules.conf ───────────────────────────────────────────────────
cat > /etc/asterisk/modules.conf <<EOF
[modules]
autoload=yes
noload => chan_sip.so
noload => chan_skinny.so
noload => chan_mgcp.so
noload => chan_motif.so
noload => res_hep.so
noload => res_hep_pjsip.so
noload => res_hep_rtcp.so
EOF

# ── rtp.conf ───────────────────────────────────────────────────────
cat > /etc/asterisk/rtp.conf <<EOF
[general]
rtpstart=10000
rtpend=10100
EOF

echo "Asterisk config généré."

# ── Services persistants (Whisper STT + Edge TTS) ─────────────────
echo "Démarrage Whisper STT (arabe)..."
python3 /usr/share/asterisk/agi-bin/whisper_service.py &

echo "Démarrage Edge TTS (ar-TN-ReemNeural)..."
python3 /usr/share/asterisk/agi-bin/edgetts_service.py &

# ── Attendre que les deux services soient prêts ───────────────────
echo "Attente des services..."
for i in $(seq 1 90); do
    W=$(curl -sf http://127.0.0.1:5001/ 2>/dev/null && echo 1 || echo 0)
    E=$(curl -sf http://127.0.0.1:5002/ 2>/dev/null && echo 1 || echo 0)
    if [ "$W" = "1" ] && [ "$E" = "1" ]; then
        echo "Whisper + EdgeTTS prêts (${i}s)"
        break
    fi
    sleep 2
done

# ── Pré-génération des fichiers audio statiques via Edge TTS ───────
echo "Génération des fichiers audio statiques (arabe tunisien)..."
python3 - <<'PYEOF'
import os, subprocess, json, urllib.request

SOUNDS_DIR = "/var/lib/asterisk/sounds"
EDGETTS_URL = "http://127.0.0.1:5002/"
os.makedirs(SOUNDS_DIR, exist_ok=True)

try:
    with open("/var/lib/asterisk/agi-bin/menu.json", encoding="utf-8") as f:
        name = json.load(f).get("restaurant", {}).get("nom", "المطعم")
except Exception:
    name = "المطعم"

PHRASES = {
    "restaurant_greeting": f"أهلاً بيك في {name}! آش تحب تطلب؟",
    "restaurant_silence":  "سمح لي، ما سمعتكش. تقدر تعاود؟",
    "restaurant_timeout":  "شكراً على اتصالك. في أمان الله!",
    "restaurant_error":    "عندنا مشكل. عاود اتصل بينا من فضلك.",
}

def edgetts_to_wav(text, wav_path):
    req = urllib.request.Request(
        EDGETTS_URL, data=text.encode("utf-8"),
        headers={"Content-Type": "text/plain; charset=utf-8"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        wav_data = resp.read()
    tmp = wav_path + ".edge.wav"
    with open(tmp, "wb") as f:
        f.write(wav_data)
    subprocess.run(
        ["ffmpeg", "-y", "-i", tmp, "-ar", "8000", "-ac", "1",
         "-acodec", "pcm_s16le", wav_path],
        capture_output=True, check=True
    )
    os.unlink(tmp)

for key, text in PHRASES.items():
    wav = f"{SOUNDS_DIR}/{key}.wav"
    try:
        edgetts_to_wav(text, wav)
        print(f"  Généré: {key}.wav")
    except Exception as e:
        print(f"  Erreur {key}: {e}")
PYEOF

echo "Démarrage Asterisk..."
exec asterisk -f -vvvv
