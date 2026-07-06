#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
ACA_LOG="${REPO_ROOT}/logs/aca-${RUN_ID}.log"
SEAGRASS_LOG="${REPO_ROOT}/logs/seagrass-${RUN_ID}.log"
WORKFLOW_NUM_THREADS="${WORKFLOW_NUM_THREADS:-ALL_CPUS}"

echo "Concurrent resource settings: GDAL_CACHEMAX=${GDAL_CACHEMAX:-8192} MB per job; threads=${WORKFLOW_NUM_THREADS} per job"

echo "Submitting ACA reef workflow"
"${SCRIPT_DIR}/run_workflow.sh" \
  --detach \
  --log-file "${ACA_LOG}" \
  --config configs/aca-workstation.yaml \
  --num-threads "${WORKFLOW_NUM_THREADS}"

echo
echo "Submitting seagrass workflow"
"${SCRIPT_DIR}/run_workflow.sh" \
  --detach \
  --log-file "${SEAGRASS_LOG}" \
  --config configs/seagrass-2023-2024.yaml \
  --num-threads "${WORKFLOW_NUM_THREADS}"

echo
echo "Both workflows have been submitted."
printf 'Monitor both logs: tail -f %q %q\n' "${ACA_LOG}" "${SEAGRASS_LOG}"
echo "Both are complete only when these files exist:"
echo "  ${REPO_ROOT}/outputs/aca_reef_habitat_v2_0/workflow-complete.json"
echo "  ${REPO_ROOT}/outputs/seagrass_2023_2024/workflow-complete.json"
