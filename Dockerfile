### Build stage: install the Python dependencies into a virtual environment
# On linux/arm/v7 the dependencies without wheels are built from source (hidapi needs libusb and libudev for that).
FROM python:3.13-slim-trixie AS build

ARG TARGETARCH

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install --yes --no-install-recommends build-essential libusb-1.0-0-dev libudev-dev && \
    apt-get clean

WORKDIR /app

COPY pyproject.toml setup.cfg README.md version.txt version_githash.txt ./
COPY linux_peripherals_controller/ ./linux_peripherals_controller/

RUN python -m venv .venv && \
    .venv/bin/pip install --no-cache-dir ".[hardware]" && \
    .venv/bin/pip uninstall --yes pip setuptools wheel && \
    find .venv -name '__pycache__' -prune -exec rm -rf {} +

### Runtime stage
FROM python:3.13-slim-trixie

ENV LANG C.UTF-8
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

LABEL \
    org.opencontainers.image.authors="Open Home Foundation" \
    org.opencontainers.image.description="Peripheral controller for Linux-Voice-Assistant (LED, button and HAT drivers)" \
    org.opencontainers.image.documentation="https://github.com/OHF-Voice/linux-peripherals-controller/blob/main/README.md" \
    org.opencontainers.image.licenses="Apache-2.0" \
    org.opencontainers.image.source="https://github.com/OHF-Voice/linux-peripherals-controller" \
    org.opencontainers.image.title="Linux-Peripherals-Controller" \
    org.opencontainers.image.url="https://github.com/OHF-Voice/linux-peripherals-controller" \
    org.opencontainers.image.vendor="Open Home Foundation"

### Install packages:
# - procps:          For pgrep in healthcheck
# - ca-certificates: For encrypted connections
# - libusb-1.0-0:    For the USB LEDs (pyusb)
# - libudev1:        For HID devices (hidapi)
RUN apt-get update && \
    apt-get install --yes --no-install-recommends \
    procps \
    ca-certificates \
    libusb-1.0-0 \
    libudev1 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man /usr/share/locale

WORKDIR /app

COPY --from=build /app/.venv ./.venv
COPY pyproject.toml setup.cfg ./
COPY linux_peripherals_controller/ ./linux_peripherals_controller/
COPY docker-entrypoint.sh ./
COPY version.txt ./
COPY version_githash.txt ./

RUN chmod +x docker-entrypoint.sh

ENTRYPOINT ["./docker-entrypoint.sh"]
