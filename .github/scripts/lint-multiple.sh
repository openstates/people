#!/bin/bash

LINT_ARGS=""
POSITIONAL=()
for arg in "$@"; do
  if [[ "$arg" == "--ignore-role-warnings" ]]; then
    LINT_ARGS+=" --ignore-role-warnings"
  else
    POSITIONAL+=("$arg")
  fi
done

if [[ -z "${ALL_CHANGED_DIRS}" ]]; then
  if [[ -z "${POSITIONAL[0]}" ]]; then
    echo "Usage: $0 <comma-separated-states> (e.g. mn,al,az) [--ignore-role-warnings]"
    echo "Or set ALL_CHANGED_DIRS environment variable"
    exit 1
  fi
  IFS=',' read -ra STATES <<< "${POSITIONAL[0]}"
  ALL_CHANGED_DIRS=""
  for state in "${STATES[@]}"; do
    ALL_CHANGED_DIRS+="data/${state} "
  done
fi

for dir in ${ALL_CHANGED_DIRS}; do
  if [[ "$dir" =~ ^data/(ak|al|ar|az|ca|co|ct|dc|de|fl|ga|hi|ia|id|il|in|ks|ky|la|ma|md|me|mi|mn|mo|ms|mt|nc|nd|ne|nh|nj|nm|nv|ny|oh|ok|or|pa|pr|ri|sc|sd|tn|tx|us|ut|va|vt|wa|wi|wv|wy) ]]; then
    dir=${BASH_REMATCH[1]}
    poetry run os-people lint "$dir"${LINT_ARGS}
  else
    echo "$dir contains changes, but ignored for linting committees"
  fi
done
