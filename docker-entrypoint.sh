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

### Start application
echo "starting application"
exec /app/.venv/bin/python -m linux_peripherals_controller "$@" "${EXTRA_ARGS[@]}"
