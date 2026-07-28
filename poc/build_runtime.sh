#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${ROOT}/build/runtime"
ZIP_FILE="${ROOT}/build/memory-poc-runtime.zip"

rm -rf "${BUILD_DIR}" "${ZIP_FILE}"
mkdir -p "${BUILD_DIR}"

uv pip install \
  --python-platform aarch64-manylinux2014 \
  --python-version 3.13 \
  --target "${BUILD_DIR}" \
  --only-binary :all: \
  --requirements "${ROOT}/poc/requirements.txt"

cp "${ROOT}/poc/runtime_agent.py" "${BUILD_DIR}/runtime_agent.py"
(
  cd "${BUILD_DIR}"
  zip -q -r "${ZIP_FILE}" .
)

echo "${ZIP_FILE}"
