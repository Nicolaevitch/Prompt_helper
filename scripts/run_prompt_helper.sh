#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/.."

python3 scripts/init_target_project.py
python3 back/server.py
