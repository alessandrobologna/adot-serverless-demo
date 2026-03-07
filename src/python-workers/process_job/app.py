import json
import os
import time
from datetime import datetime, timezone

import boto3


TABLE = boto3.resource("dynamodb").Table(os.environ["JOBS_TABLE_NAME"])
S3_CLIENT = boto3.client("s3")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def handler(event, _context):
    processed = []

    for record in event.get("Records", []):
        message = json.loads(record["body"])
        job_id = message["jobId"]
        mode = message.get("mode", "ok")
        current_time = now_iso()

        TABLE.update_item(
            Key={"jobId": job_id},
            UpdateExpression="SET #status = :status, updatedAt = :updatedAt REMOVE errorMessage",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": "PROCESSING",
                ":updatedAt": current_time,
            },
        )

        if mode == "slow":
            time.sleep(int(os.environ.get("DEMO_SLOW_DELAY_SECONDS", "6")))

        if mode == "fail":
            error_message = "Simulated worker failure triggered by mode=fail."
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

        processed.append({"jobId": job_id, "status": "COMPLETED"})

    return {"processed": processed}
