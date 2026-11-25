# Linux-Peripherals-Controller - Installation

LPC runs as a Docker container next to [Linux-Voice-Assistant](https://github.com/OHF-Voice/linux-voice-assistant) (LVA) and connects to its peripheral WebSocket API on port 6055.

## Prerequisites

- A running LVA with the peripheral API enabled (it is on by default)
- Docker and Docker Compose

## Docker Compose

```sh
git clone https://github.com/OHF-Voice/linux-peripherals-controller.git
cd linux-peripherals-controller
cp .env.example .env
docker compose up -d
docker compose logs -f
```

The container uses `network_mode: host`, so `localhost` reaches LVA when both run on the same machine. If LVA runs on another machine, set `LVA_HOST` in `.env`.

Hardware access (GPIO, SPI, I2C, PWM, USB) is added to `docker-compose.yml` together with the peripheral drivers.

## Development image

`docker-compose.dev.yml` uses the `nightly` image of the PR registry and mounts the source code into the container:

```sh
docker compose -f docker-compose.dev.yml up
```
