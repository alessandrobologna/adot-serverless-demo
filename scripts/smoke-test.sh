#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 <stack-name> [aws-region]" >&2
  exit 1
fi

STACK_NAME="$1"
AWS_REGION="${2:-us-east-1}"

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

poll_job_status() {
  local api_base_url="$1"
  local job_id="$2"
  local expected_statuses="$3"
  local deadline=$((SECONDS + 90))

  while (( SECONDS < deadline )); do
    local body
    body="$(curl -fsS "${api_base_url}/jobs/${job_id}")"
    local status
    status="$(printf '%s' "${body}" | json_field "status")"

    if [[ " ${expected_statuses} " == *" ${status} "* ]]; then
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
ARTIFACTS_BUCKET_NAME="$(stack_output ArtifactsBucketName)"
WORK_DLQ_URL="$(stack_output WorkDlqUrl)"

if [[ -z "${API_BASE_URL}" || -z "${ARTIFACTS_BUCKET_NAME}" || -z "${WORK_DLQ_URL}" ]]; then
  echo "Unable to resolve required CloudFormation outputs." >&2
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

echo "API base URL: ${API_BASE_URL}"
echo "Submitting ok, slow, and fail jobs..."

ok_submit="$(submit_job "${API_BASE_URL}" ok)"
slow_submit="$(submit_job "${API_BASE_URL}" slow)"
fail_submit="$(submit_job "${API_BASE_URL}" fail)"

ok_job_id="$(printf '%s' "${ok_submit}" | json_field "jobId")"
slow_job_id="$(printf '%s' "${slow_submit}" | json_field "jobId")"
fail_job_id="$(printf '%s' "${fail_submit}" | json_field "jobId")"

ok_job="$(poll_job_status "${API_BASE_URL}" "${ok_job_id}" "COMPLETED")"
slow_job="$(poll_job_status "${API_BASE_URL}" "${slow_job_id}" "COMPLETED")"
fail_job="$(poll_job_status "${API_BASE_URL}" "${fail_job_id}" "FAILED")"

ok_artifact_key="$(printf '%s' "${ok_job}" | json_field "artifactKey")"
slow_artifact_key="$(printf '%s' "${slow_job}" | json_field "artifactKey")"

aws s3api head-object \
  --bucket "${ARTIFACTS_BUCKET_NAME}" \
  --key "${ok_artifact_key}" \
  --region "${AWS_REGION}" >/dev/null

aws s3api head-object \
  --bucket "${ARTIFACTS_BUCKET_NAME}" \
  --key "${slow_artifact_key}" \
  --region "${AWS_REGION}" >/dev/null

fail_deadline=$((SECONDS + 60))
final_dlq_count="${initial_dlq_count}"
while (( SECONDS < fail_deadline )); do
  final_dlq_count="$(
    aws sqs get-queue-attributes \
      --queue-url "${WORK_DLQ_URL}" \
      --region "${AWS_REGION}" \
      --attribute-names ApproximateNumberOfMessages \
      --query 'Attributes.ApproximateNumberOfMessages' \
      --output text
  )"

  if (( final_dlq_count > initial_dlq_count )); then
    break
  fi

  sleep 5
done

if (( final_dlq_count <= initial_dlq_count )); then
  echo "Expected the fail-mode job to increase the DLQ depth, but it did not." >&2
  exit 1
fi

echo "Smoke test complete."
echo "  ok job:   ${ok_job_id}"
echo "  slow job: ${slow_job_id}"
echo "  fail job: ${fail_job_id}"
echo "  DLQ depth moved from ${initial_dlq_count} to ${final_dlq_count}"
