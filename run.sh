#!/usr/bin/env bash
# =============================================================================
#  EDUX ULTIMATE LIFEFORM v0.7 - LAUNCHER GỐC CHO LINUX
# =============================================================================
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
exec bash "$DIR/edux-auto-solver/run.sh" "$@"
