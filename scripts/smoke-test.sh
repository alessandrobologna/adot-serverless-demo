#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
usage: smoke-test.sh <stack-name> [aws-region] [--count N] [--modes ok,slow,fail]

Defaults:
  aws-region: us-east-1
  count:      1
  modes:      ok,slow,fail

Notes:
  --count applies per mode. For example, --modes ok --count 100 submits 100 ok jobs.
  Successful jobs are not considered complete until they reach COMPLETED and the
  indexer has written artifactIndexedAt.
EOF
}

STACK_NAME=""
AWS_REGION="us-east-1"
COUNT=1
MODES_CSV="ok,slow,fail"
AWS_REGION_SET="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --count)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --count." >&2
        usage
        exit 1
      fi
      COUNT="$2"
      shift 2
      ;;
    --modes)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --modes." >&2
        usage
        exit 1
      fi
      MODES_CSV="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
    *)
      if [[ -z "${STACK_NAME}" ]]; then
        STACK_NAME="$1"
      elif [[ "${AWS_REGION_SET}" == "false" ]]; then
        AWS_REGION="$1"
        AWS_REGION_SET="true"
      else
        echo "Too many positional arguments." >&2
        usage
        exit 1
      fi
      shift
      ;;
  esac
done

if [[ -z "${STACK_NAME}" ]]; then
  usage
  exit 1
fi

if ! [[ "${COUNT}" =~ ^[1-9][0-9]*$ ]]; then
  echo "--count must be a positive integer." >&2
  exit 1
fi

IFS=',' read -r -a REQUESTED_MODES <<<"${MODES_CSV}"
if [[ ${#REQUESTED_MODES[@]} -eq 0 ]]; then
  echo "--modes must include at least one mode." >&2
  exit 1
fi

VALIDATED_MODES=()
for mode in "${REQUESTED_MODES[@]}"; do
  mode="${mode//[[:space:]]/}"
  case "${mode}" in
    ok|slow|fail)
      VALIDATED_MODES+=("${mode}")
      ;;
    "")
      echo "--modes contains an empty mode value." >&2
      exit 1
      ;;
    *)
      echo "Unsupported mode '${mode}'. Supported modes: ok, slow, fail." >&2
      exit 1
      ;;
  esac
done

REQUESTED_MODES=("${VALIDATED_MODES[@]}")

stack_output() {
  local key="$1"
  aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${AWS_REGION}" \
    --query "Stacks[0].Outputs[?OutputKey==\`${key}\`].OutputValue" \
    --output text
}

json_field() {
  local field="$1"
  python3 -c '
import json
import sys

field = sys.argv[1]
payload = json.load(sys.stdin)
value = payload
for key in field.split("."):
    if key:
        value = value[key]
print(value)
' "$field"
}

json_field_optional() {
  local field="$1"
  python3 -c '
import json
import sys

field = sys.argv[1]
payload = json.load(sys.stdin)
value = payload
try:
    for key in field.split("."):
        if key:
            value = value[key]
except (KeyError, TypeError):
    value = ""

if value is None:
    value = ""

print(value)
' "$field"
}

poll_job_status() {
  local api_base_url="$1"
  local job_id="$2"
  local expected_statuses="$3"
  local required_field="${4:-}"
  local deadline=$((SECONDS + 90))

  while (( SECONDS < deadline )); do
    local body
    body="$(curl -fsS "${api_base_url}/jobs/${job_id}")"
    local status
    status="$(printf '%s' "${body}" | json_field "status")"

    if [[ " ${expected_statuses} " == *" ${status} "* ]]; then
      if [[ -n "${required_field}" ]]; then
        local required_value
        required_value="$(printf '%s' "${body}" | json_field_optional "${required_field}")"
        if [[ -z "${required_value}" ]]; then
          sleep 3
          continue
        fi
      fi

      printf '%s' "${body}"
      return 0
    fi

    sleep 3
  done

  echo "Timed out waiting for ${job_id} to reach one of: ${expected_statuses}" >&2
  return 1
}

submit_job() {
  local api_base_url="$1"
  local mode="$2"
  curl -fsS \
    -X POST \
    -H "content-type: application/json" \
    -d "{\"mode\":\"${mode}\"}" \
    "${api_base_url}/jobs"
}

API_BASE_URL="$(stack_output ApiBaseUrl)"

if [[ -z "${API_BASE_URL}" ]]; then
  echo "Unable to resolve required CloudFormation outputs." >&2
  exit 1
fi

ARTIFACTS_BUCKET_NAME=""
WORK_DLQ_URL=""
needs_artifact_checks="false"
needs_dlq_check="false"

for mode in "${REQUESTED_MODES[@]}"; do
  case "${mode}" in
    ok|slow)
      needs_artifact_checks="true"
      ;;
    fail)
      needs_dlq_check="true"
      ;;
  esac
done

if [[ "${needs_artifact_checks}" == "true" ]]; then
  ARTIFACTS_BUCKET_NAME="$(stack_output ArtifactsBucketName)"
  if [[ -z "${ARTIFACTS_BUCKET_NAME}" ]]; then
    echo "Unable to resolve ArtifactsBucketName." >&2
    exit 1
  fi
fi

initial_dlq_count=0
if [[ "${needs_dlq_check}" == "true" ]]; then
  WORK_DLQ_URL="$(stack_output WorkDlqUrl)"
  if [[ -z "${WORK_DLQ_URL}" ]]; then
    echo "Unable to resolve WorkDlqUrl." >&2
    exit 1
  fi

  initial_dlq_count="$(
    aws sqs get-queue-attributes \
      --queue-url "${WORK_DLQ_URL}" \
      --region "${AWS_REGION}" \
      --attribute-names ApproximateNumberOfMessages \
      --query 'Attributes.ApproximateNumberOfMessages' \
      --output text
  )"
fi

echo "API base URL: ${API_BASE_URL}"
echo "Submitting ${COUNT} job(s) for each mode: ${REQUESTED_MODES[*]}"

submitted_total=0
submitted_fail_count=0
submitted_modes=()
submitted_job_ids=()
ok_job_ids=()
slow_job_ids=()
fail_job_ids=()

for mode in "${REQUESTED_MODES[@]}"; do
  for ((i = 1; i <= COUNT; i++)); do
    submit_body="$(submit_job "${API_BASE_URL}" "${mode}")"
    job_id="$(printf '%s' "${submit_body}" | json_field "jobId")"
    submitted_modes+=("${mode}")
    submitted_job_ids+=("${job_id}")
    submitted_total=$((submitted_total + 1))
    if [[ "${mode}" == "fail" ]]; then
      submitted_fail_count=$((submitted_fail_count + 1))
    fi
  done
done

for idx in "${!submitted_job_ids[@]}"; do
  mode="${submitted_modes[$idx]}"
  job_id="${submitted_job_ids[$idx]}"

  expected_status="COMPLETED"
  required_field="artifactIndexedAt"
  if [[ "${mode}" == "fail" ]]; then
    expected_status="FAILED"
    required_field=""
  fi

  job_body="$(poll_job_status "${API_BASE_URL}" "${job_id}" "${expected_status}" "${required_field}")"

  case "${mode}" in
    ok|slow)
      artifact_key="$(printf '%s' "${job_body}" | json_field "artifactKey")"
      aws s3api head-object \
        --bucket "${ARTIFACTS_BUCKET_NAME}" \
        --key "${artifact_key}" \
        --region "${AWS_REGION}" >/dev/null
      ;;
  esac

  case "${mode}" in
    ok)
      ok_job_ids+=("${job_id}")
      ;;
    slow)
      slow_job_ids+=("${job_id}")
      ;;
    fail)
      fail_job_ids+=("${job_id}")
      ;;
  esac
done

final_dlq_count="${initial_dlq_count}"
if [[ "${needs_dlq_check}" == "true" ]]; then
  expected_dlq_count=$((initial_dlq_count + submitted_fail_count))
  fail_deadline=$((SECONDS + 60 + (submitted_fail_count * 5)))

  while (( SECONDS < fail_deadline )); do
    final_dlq_count="$(
      aws sqs get-queue-attributes \
        --queue-url "${WORK_DLQ_URL}" \
        --region "${AWS_REGION}" \
        --attribute-names ApproximateNumberOfMessages \
        --query 'Attributes.ApproximateNumberOfMessages' \
        --output text
    )"

    if (( final_dlq_count >= expected_dlq_count )); then
      break
    fi

    sleep 5
  done

  if (( final_dlq_count < expected_dlq_count )); then
    echo "Expected ${submitted_fail_count} fail-mode job(s) to increase the DLQ depth from ${initial_dlq_count} to at least ${expected_dlq_count}, but it reached ${final_dlq_count}." >&2
    exit 1
  fi
fi

print_job_summary() {
  local label="$1"
  local outcome="$2"
  shift 2
  local job_count=$#

  if (( job_count == 0 )); then
    return 0
  fi

  if (( job_count == 1 )); then
    printf '  %s job:   %s\n' "${label}" "$1"
    return 0
  fi

  if (( job_count <= 5 )); then
    printf '  %s jobs:  %s\n' "${label}" "$*"
    return 0
  fi

  local first_job="$1"
  local last_job="${!job_count}"
  printf '  %s jobs:  %d %s (first %s, last %s)\n' "${label}" "${job_count}" "${outcome}" "${first_job}" "${last_job}"
}

echo "Smoke test complete."
echo "  submitted: ${submitted_total}"
if (( ${#ok_job_ids[@]} > 0 )); then
  print_job_summary "ok" "completed" "${ok_job_ids[@]}"
fi
if (( ${#slow_job_ids[@]} > 0 )); then
  print_job_summary "slow" "completed" "${slow_job_ids[@]}"
fi
if (( ${#fail_job_ids[@]} > 0 )); then
  print_job_summary "fail" "failed" "${fail_job_ids[@]}"
fi
if [[ "${needs_dlq_check}" == "true" ]]; then
  echo "  DLQ depth moved from ${initial_dlq_count} to ${final_dlq_count}"
fi
