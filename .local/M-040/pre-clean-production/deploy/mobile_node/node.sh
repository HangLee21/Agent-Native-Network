#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
exec python3 -m tools.mobile_node node "$@"
