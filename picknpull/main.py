"""Compatibility entry point; shared integrations live in junkyard.providers."""
from junkyard.worker import main

if __name__ == '__main__':
    raise SystemExit(main(['picknpull']))
