#!/bin/sh

# Check if both health status files contain only the word "healthy"
if [ "$(cat /tmp/UTPAP/health_status.txt)" = "healthy" ] && [ "$(cat /tmp/tearapart/health_status.txt)" = "healthy" ]; then
  exit 0
else
  exit 1
fi
