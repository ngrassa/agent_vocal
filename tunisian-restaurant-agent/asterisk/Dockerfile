FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    asterisk \
    python3 python3-pip \
    ffmpeg sox \
    libgsm1 \
    curl \
    espeak-ng \
    espeak-ng-data \
    && rm -rf /var/lib/apt/lists/*

# Python deps for AGI script
COPY agi/requirements.txt /tmp/agi_requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/agi_requirements.txt

# AGI scripts
COPY agi/ /usr/share/asterisk/agi-bin/
RUN chmod +x /usr/share/asterisk/agi-bin/*.py

# Entrypoint
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 5060/udp 5060/tcp 10000-10100/udp

ENTRYPOINT ["/start.sh"]
