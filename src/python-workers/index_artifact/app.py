import os
from datetime import datetime, timezone
from urllib.parse import unquote_plus

import boto3

try:
    from opentelemetry import trace
except ImportError:
    trace = None


TABLE = boto3.resource("dynamodb").Table(os.environ["JOBS_TABLE_NAME"])
S3_CLIENT = boto3.client("s3")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_span_event(name: str, attributes: dict | None = None) -> None:
    if trace is None:
        return

    trace.get_current_span().add_event(name, attributes or {})


def handler(event, _context):
    indexed = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        if not key.startswith("artifacts/") or not key.endswith(".json"):
            add_span_event(
                "demo.artifact.skipped",
                {
                    "bucket": bucket,
                    "key": key,
                },
            )
            continue

        add_span_event(
            "demo.artifact.indexing.started",
            {
                "bucket": bucket,
                "key": key,
            },
        )

        head = S3_CLIENT.head_object(Bucket=bucket, Key=key)
        job_id = key.rsplit("/", 1)[-1].removesuffix(".json")
        indexed_at = now_iso()

        add_span_event(
            "demo.artifact.metadata.loaded",
            {
                "artifactSize": head["ContentLength"],
                "bucket": bucket,
                "contentType": head.get("ContentType", "application/octet-stream"),
                "jobId": job_id,
                "key": key,
            },
        )

        TABLE.update_item(
            Key={"jobId": job_id},
            UpdateExpression=(
                "SET artifactContentType = :contentType, artifactIndexedAt = :indexedAt, "
                "artifactSize = :artifactSize, updatedAt = :updatedAt"
            ),
            ExpressionAttributeValues={
                ":artifactSize": head["ContentLength"],
                ":contentType": head.get("ContentType", "application/octet-stream"),
                ":indexedAt": indexed_at,
                ":updatedAt": indexed_at,
            },
        )

        add_span_event(
            "demo.artifact.indexed",
            {
                "bucket": bucket,
                "jobId": job_id,
                "key": key,
            },
        )
        indexed.append({"bucket": bucket, "jobId": job_id, "key": key})

    return {"indexed": indexed}
