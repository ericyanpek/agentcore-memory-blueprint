#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYER_DIR="${ROOT}/infra/layer/python"

find "${LAYER_DIR}" -mindepth 1 ! -name .gitkeep -exec rm -rf {} +

uv pip install \
  --python-platform aarch64-manylinux2014 \
  --python-version 3.12 \
  --target "${LAYER_DIR}" \
  --only-binary :all: \
  --requirements "${ROOT}/src/requirements.txt"

echo "${LAYER_DIR}"
