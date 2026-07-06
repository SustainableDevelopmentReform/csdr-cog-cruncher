#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"

DETACH=false
LOG_FILE=""
WORKFLOW_ARGS=()

while (($#)); do
  case "$1" in
    --detach)
      DETACH=true
      shift
      ;;
    --log-file)
      if (($# < 2)); then
        echo "Error: --log-file requires a path." >&2
        exit 2
      fi
      LOG_FILE="$2"
      shift 2
      ;;
    --log-file=*)
      LOG_FILE="${1#*=}"
      shift
      ;;
    --)
      shift
      WORKFLOW_ARGS+=("$@")
      break
      ;;
    *)
      WORKFLOW_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ -n "${LOG_FILE}" && "${DETACH}" != true ]]; then
  echo "Error: --log-file can only be used with --detach." >&2
  exit 2
fi

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

if [[ "${DETACH}" == true ]]; then
  if [[ -z "${LOG_FILE}" ]]; then
    LOG_FILE="${REPO_ROOT}/logs/workflow-$(date +%Y%m%d-%H%M%S).log"
  elif [[ "${LOG_FILE}" != /* ]]; then
    LOG_FILE="${PWD}/${LOG_FILE}"
  fi
  mkdir -p -- "$(dirname -- "${LOG_FILE}")"

  (
    cd "${REPO_ROOT}"
    "${PYTHON_BIN}" -m csdr_cog_cruncher.cli "${WORKFLOW_ARGS[@]}" --show-outputs
  )

  CSDR_WORKFLOW_DETACHED=1 nohup "${SCRIPT_DIR}/run_workflow.sh" "${WORKFLOW_ARGS[@]}" \
    </dev/null >"${LOG_FILE}" 2>&1 &
  WORKFLOW_PID=$!

  echo "Workflow submitted in the background."
  echo "PID: ${WORKFLOW_PID}"
  echo "Log: ${LOG_FILE}"
  printf 'Monitor: tail -f %q\n' "${LOG_FILE}"
  exit 0
fi

echo "GDAL cache: ${GDAL_CACHEMAX} MB"
if [[ "${CSDR_WORKFLOW_DETACHED:-}" == 1 ]]; then
  echo "Workflow PID: $$"
fi
cd "${REPO_ROOT}"
exec "${PYTHON_BIN}" -m csdr_cog_cruncher.cli "${WORKFLOW_ARGS[@]}"
