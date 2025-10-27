#!/bin/sh
set -e

# Decide which upstream is backup based on ACTIVE_POOL env
BLUE_BACKUP=""
GREEN_BACKUP=""
if [ "$ACTIVE_POOL" = "blue" ]; then
  BLUE_BACKUP=""
  GREEN_BACKUP="backup"
elif [ "$ACTIVE_POOL" = "green" ]; then
  BLUE_BACKUP="backup"
  GREEN_BACKUP=""
else
  echo "WARNING: ACTIVE_POOL is not 'blue' or 'green' (got '$ACTIVE_POOL'). Defaulting to blue active."
  BLUE_BACKUP=""
  GREEN_BACKUP="backup"
fi

export BLUE_BACKUP GREEN_BACKUP

# Render nginx.conf
envsubst '$BLUE_BACKUP $GREEN_BACKUP' < /etc/nginx/user-templates/nginx.conf.template > /etc/nginx/conf.d/default.conf

# Continue to normal nginx startup
