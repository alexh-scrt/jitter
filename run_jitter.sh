#!/usr/bin/env bash
# Jitter daily cron script
# Runs the jitter pipeline once using the conda 'jitter' environment.
# Scheduled via cron for 3:00 AM EST daily.
#
# Install:  crontab -e  then add:
#   0 3 * * * /home/ubuntu/jitter/run_jitter.sh
#
# Note: macOS cron uses the system timezone. If your Mac is set to EST/ET,
# use "0 3 * * *". If set to UTC, use "0 8 * * *" (3 AM EST = 8 AM UTC).

set -xeuo pipefail

# --- Configuration ---
if [ -e ${HOME}/miniconda3 ]; then
    CONDA_PYTHON="${HOME}/miniconda3/envs/jitter/bin/python"
else
    CONDA_PYTHON="${HOME}/miniconda/envs/jitter/bin/python"
fi

PROJECT_DIR="${HOME}/jitter"
LOG_DIR="${PROJECT_DIR}/logs"
TIMESTAMP=$(date +"%Y-%m-%d_%H%M%S")
LOG_FILE="${LOG_DIR}/jitter_${TIMESTAMP}.log"

# --- Setup ---
mkdir -p "${LOG_DIR}"

echo "=== Jitter Run: $(date) ===" | tee -a "${LOG_FILE}"
echo "Python: ${CONDA_PYTHON}" | tee -a "${LOG_FILE}"
echo "Working dir: ${PROJECT_DIR}" | tee -a "${LOG_FILE}"

# --- Load API keys from .env ---
if [ -f "${PROJECT_DIR}/.env" ]; then
    set -a
    source "${PROJECT_DIR}/.env"
    set +a
    echo "* Loaded .env" | tee -a "${LOG_FILE}"
    echo "GITHUB_TOKEN: ${GITHUB_TOKEN:0:4}... (length: ${#GITHUB_TOKEN})" | tee -a "${LOG_FILE}"
    echo "ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:0:4}... (length: ${#ANTHROPIC_API_KEY})" | tee -a "${LOG_FILE}"
    echo "TAVILY_API_KEY: ${TAVILY_API_KEY:0:4}... (length: ${#TAVILY_API_KEY})" | tee -a "${LOG_FILE}"
else
    echo "ERROR: .env file not found at ${PROJECT_DIR}/.env" | tee -a "${LOG_FILE}"
    exit 1
fi

echo "TEST ---"

# --- Run Jitter ---
cd "${PROJECT_DIR}"
"${CONDA_PYTHON}" -m jitter run --config config.yaml >> "${LOG_FILE}" 2>&1
EXIT_CODE=$?

# --- Report ---
if [ ${EXIT_CODE} -eq 0 ]; then
    echo "=== Completed successfully: $(date) ===" | tee -a "${LOG_FILE}"
else
    echo "=== FAILED (exit code ${EXIT_CODE}): $(date) ===" | tee -a "${LOG_FILE}"
fi

# --- Cleanup old logs (keep last 30 days) ---
find "${LOG_DIR}" -name "jitter_*.log" -mtime +30 -delete 2>/dev/null

exit ${EXIT_CODE}

