# Linux Peripheral Controller - Installation

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

The container runs `privileged`, so it reaches the hardware of every device type: GPIO (`/dev/gpiochip*`), SPI (`/dev/spidev*`), USB (`/dev/bus/usb`) and HID (`/dev/hidraw*`). The child lock, the light and the encryption key are kept in `./data` next to `docker-compose.yml`.

For the ReSpeaker HATs, SPI has to be enabled on the Raspberry Pi: add `dtparam=spi=on` to `/boot/firmware/config.txt` and reboot (the Seeed driver installer does this).

Home Assistant discovers LPC over mDNS as an ESPHome device (port `6054`). Add it in the ESPHome integration. With `ENABLE_ZEROCONF="0"` add it by hand with the IP address of the machine and port `6054`.

## Development image

`docker-compose.dev.yml` uses the `nightly` image of the PR registry and mounts the source code into the container:

```sh
docker compose -f docker-compose.dev.yml up
```
