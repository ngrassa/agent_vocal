FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    asterisk \
    python3 python3-pip \
    ffmpeg sox \
    libgsm1 \
    curl \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

# Python deps for AGI script
COPY agi/requirements.txt /tmp/agi_requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/agi_requirements.txt

# Modèle Piper TTS français — voix féminine naturelle (fr_FR-upmc-medium, ~63 MB)
RUN mkdir -p /opt/piper-voices && \
    python3 -c "\
import urllib.request; \
b='https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/upmc/medium/'; \
urllib.request.urlretrieve(b+'fr_FR-upmc-medium.onnx',      '/opt/piper-voices/fr.onnx'); \
urllib.request.urlretrieve(b+'fr_FR-upmc-medium.onnx.json', '/opt/piper-voices/fr.onnx.json'); \
print('Piper voice OK.')"

# AGI scripts — Asterisk (Ubuntu pkg) cherche dans /usr/share/asterisk/agi-bin
COPY agi/ /usr/share/asterisk/agi-bin/
RUN chmod +x /usr/share/asterisk/agi-bin/*.py

# Entrypoint
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 5060/udp 5060/tcp 10000-10100/udp

ENTRYPOINT ["/start.sh"]
