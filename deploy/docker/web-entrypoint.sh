#!/usr/bin/env sh
set -eu

APP_ENV="${NEXT_PUBLIC_APP_ENV:-local}"
USE_FIXTURES="${NEXT_PUBLIC_USE_FIXTURES:-true}"

if [ "$APP_ENV" = "staging" ] || [ "$APP_ENV" = "production" ]; then
  if [ "$USE_FIXTURES" != "false" ]; then
    echo "Refusing to start web container: fixture mode must be disabled in ${APP_ENV}." >&2
    exit 1
  fi
fi

exec node server.js
