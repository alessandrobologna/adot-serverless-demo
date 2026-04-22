import json
import os
import time
from datetime import datetime, timezone
from typing import Optional

import boto3

try:
    from opentelemetry import trace
except ImportError:
    trace = None


TABLE = boto3.resource("dynamodb").Table(os.environ["JOBS_TABLE_NAME"])
S3_CLIENT = boto3.client("s3")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_span_event(name: str, attributes: Optional[dict] = None) -> None:
    if trace is None:
        return

    trace.get_current_span().add_event(name, attributes or {})


def handler(event, _context):
    processed = []

    for record in event.get("Records", []):
        message = json.loads(record["body"])
        job_id = message["jobId"]
        mode = message.get("mode", "ok")
        current_time = now_iso()

        add_span_event(
            "demo.job.received",
            {
                "jobId": job_id,
                "mode": mode,
            },
        )

        TABLE.update_item(
            Key={"jobId": job_id},
            UpdateExpression="SET #status = :status, updatedAt = :updatedAt REMOVE errorMessage",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": "PROCESSING",
                ":updatedAt": current_time,
            },
        )

        add_span_event(
            "demo.job.processing.started",
            {
                "jobId": job_id,
                "mode": mode,
                "status": "PROCESSING",
            },
        )

        if mode == "slow":
            delay_seconds = int(os.environ.get("DEMO_SLOW_DELAY_SECONDS", "6"))
            add_span_event(
                "demo.job.delay.applied",
                {
                    "jobId": job_id,
                    "delaySeconds": delay_seconds,
                },
            )
            time.sleep(delay_seconds)

        if mode == "fail":
            error_message = "Simulated worker failure triggered by mode=fail."
            add_span_event(
                "demo.job.failure.simulated",
                {
                    "jobId": job_id,
                    "mode": mode,
                    "errorMessage": error_message,
                },
            )
            TABLE.update_item(
                Key={"jobId": job_id},
                UpdateExpression=(
                    "SET #status = :status, errorMessage = :errorMessage, updatedAt = :updatedAt"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":status": "FAILED",
                    ":errorMessage": error_message,
                    ":updatedAt": now_iso(),
                },
            )
            raise RuntimeError(error_message)

        artifact_key = f"artifacts/{job_id}.json"
        artifact_body = {
            "completedAt": now_iso(),
            "jobId": job_id,
            "mode": mode,
            "status": "COMPLETED",
        }

        S3_CLIENT.put_object(
            Bucket=os.environ["ARTIFACTS_BUCKET_NAME"],
            Key=artifact_key,
            Body=json.dumps(artifact_body, sort_keys=True).encode("utf-8"),
            ContentType="application/json",
        )

        add_span_event(
            "demo.artifact.written",
            {
                "artifactKey": artifact_key,
                "bucket": os.environ["ARTIFACTS_BUCKET_NAME"],
                "jobId": job_id,
            },
        )

        TABLE.update_item(
            Key={"jobId": job_id},
            UpdateExpression=(
                "SET #status = :status, artifactKey = :artifactKey, updatedAt = :updatedAt REMOVE errorMessage"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": "COMPLETED",
                ":artifactKey": artifact_key,
                ":updatedAt": now_iso(),
            },
        )

        add_span_event(
            "demo.job.processing.completed",
            {
                "artifactKey": artifact_key,
                "jobId": job_id,
                "status": "COMPLETED",
            },
        )

        processed.append({"jobId": job_id, "status": "COMPLETED"})

    return {"processed": processed}
