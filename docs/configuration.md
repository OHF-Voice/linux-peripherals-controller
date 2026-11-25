# Configuration

LPC is configured with command line options. In Docker, set the environment variable of an option in `.env` (see `.env.example`).

| Option | Environment variable | Default | Description |
|--------|----------------------|---------|-------------|
| `--lva-host` | `LVA_HOST` | `localhost` | Host of the LVA peripheral WebSocket API. |
| `--lva-port` | `LVA_PORT` | `6055` | Port of the LVA peripheral WebSocket API. |
| `--debug` | `ENABLE_DEBUG` | off | Print DEBUG messages to console. In Docker set `ENABLE_DEBUG="1"`. |

Docker Compose only:

| Environment variable | Default | Description |
|----------------------|---------|-------------|
| `LPC_IMAGE` | `ghcr.io/ohf-voice/linux-peripherals-controller` | Docker image to use. |
| `LPC_IMAGE_TAG` | `latest` (`nightly` in the dev file) | Tag of the Docker image. |
