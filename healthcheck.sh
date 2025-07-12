#!/bin/sh

# Check if all health status files contain only the word "healthy"
if [ "$(cat /tmp/jacks/health_status.txt)" = "healthy" ] && [ "$(cat /tmp/LKQ/health_status.txt)" = "healthy" ] && [ "$(cat /tmp/picknpull/health_status.txt)" = "healthy" ] && [ "$(cat /tmp/pullapart/health_status.txt)" = "healthy" ] && [ "$(cat /tmp/upullandsave/health_status.txt)" = "healthy" ]; then
  exit 0
else
  exit 1
fi
