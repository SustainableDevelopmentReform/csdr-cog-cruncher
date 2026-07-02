#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"

if [[ -x "${VENV_DIR}/bin/python" && -z "${PYTHON:-}" ]]; then
  PYTHON_BIN="${VENV_DIR}/bin/python"
else
  PYTHON_BIN="${PYTHON:-python3}"
fi

if ! "${PYTHON_BIN}" -c 'import csdr_cog_cruncher' >/dev/null 2>&1; then
  if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    echo "Creating Python environment at ${VENV_DIR}"
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  fi
  PYTHON_BIN="${VENV_DIR}/bin/python"
  echo "Installing csdr-cog-cruncher into ${VENV_DIR}"
  "${PYTHON_BIN}" -m pip install -e "${REPO_ROOT}"
fi

export GDAL_CACHEMAX="${GDAL_CACHEMAX:-8192}"

echo "GDAL cache: ${GDAL_CACHEMAX} MB"
cd "${REPO_ROOT}"
exec "${PYTHON_BIN}" -m csdr_cog_cruncher.cli "$@"
