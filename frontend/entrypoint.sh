#!/bin/sh
set -e
# Render only the variables this template references, so nginx variables such
# as $uri, $host and $scheme are left untouched.
envsubst '$PORT $BACKEND_SCHEME $BACKEND_TARGET' \
    < /etc/nginx/templates/default.conf.template \
    > /etc/nginx/conf.d/default.conf
exec nginx -g "daemon off;"