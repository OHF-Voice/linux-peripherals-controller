#!/bin/bash
set -e

### Handlers
# Handle parameters
EXTRA_ARGS=()

if [ "$ENABLE_DEBUG" = "1" ]; then
  EXTRA_ARGS+=( "--debug" )
fi

if [ -n "${DEVICE_TYPE}" ]; then
  EXTRA_ARGS+=( "--device-type" "$DEVICE_TYPE" )
fi

if [ -n "${DEVICE_CONFIG}" ]; then
  EXTRA_ARGS+=( "--device-config" "$DEVICE_CONFIG" )
fi

if [ -n "${LVA_HOST}" ]; then
  EXTRA_ARGS+=( "--lva-host" "$LVA_HOST" )
fi

if [ -n "${LVA_PORT}" ]; then
  EXTRA_ARGS+=( "--lva-port" "$LVA_PORT" )
fi

if [ -n "${CLIENT_NAME}" ]; then
  EXTRA_ARGS+=( "--name" "$CLIENT_NAME" )
fi

if [ -n "${HOST}" ]; then
  EXTRA_ARGS+=( "--host" "$HOST" )
fi

if [ -n "${PORT}" ]; then
  EXTRA_ARGS+=( "--port" "$PORT" )
fi

if [ -n "${ENABLE_ZEROCONF}" ]; then
  EXTRA_ARGS+=( "--enable-zeroconf" "$ENABLE_ZEROCONF" )
fi

if [ "$ENABLE_ENCRYPTION" = "1" ]; then
  EXTRA_ARGS+=( "--enable-encryption" )
fi

if [ -n "${ENCRYPTION_KEY_FILE}" ]; then
  EXTRA_ARGS+=( "--encryption-key-file" "$ENCRYPTION_KEY_FILE" )
fi

# The state (child lock, light) and the encryption key are kept in the data volume
STATE_FILE=${STATE_FILE:-/data/state.json}
EXTRA_ARGS+=( "--state-file" "$STATE_FILE" )

if [ "$SIMULATE_HARDWARE" = "1" ]; then
  EXTRA_ARGS+=( "--simulate-hardware" )
fi

### Start application
echo "starting application"
exec /app/.venv/bin/python -m linux_peripherals_controller "$@" "${EXTRA_ARGS[@]}"
