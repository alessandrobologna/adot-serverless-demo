import os
from datetime import datetime, timezone
from urllib.parse import unquote_plus

import boto3


TABLE = boto3.resource("dynamodb").Table(os.environ["JOBS_TABLE_NAME"])
S3_CLIENT = boto3.client("s3")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def handler(event, _context):
    indexed = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        if not key.startswith("artifacts/") or not key.endswith(".json"):
            continue

        head = S3_CLIENT.head_object(Bucket=bucket, Key=key)
        job_id = key.rsplit("/", 1)[-1].removesuffix(".json")
        indexed_at = now_iso()

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
        indexed.append({"bucket": bucket, "jobId": job_id, "key": key})

    return {"indexed": indexed}
