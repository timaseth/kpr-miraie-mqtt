ARG BUILD_FROM=ghcr.io/hassio-addons/base:20.0.4
FROM ${BUILD_FROM}

# Install Python 3, pip, jq and curl via apk (Alpine package manager)
# jq   — parse /data/options.json in run.sh
# curl — query Supervisor MQTT service API in run.sh
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-yaml \
    jq \
    curl

WORKDIR /app

# Install Python package requirements
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copy bridge source
COPY miraie_bridge.py .

# Copy and permission the entrypoint
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
