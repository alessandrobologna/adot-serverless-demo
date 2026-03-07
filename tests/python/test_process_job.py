import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROCESS_JOB_PATH = (
    Path(__file__).resolve().parents[2] / "src/python-workers/process_job/app.py"
)


class FakeTable:
    def __init__(self):
        self.updates = []

    def update_item(self, **kwargs):
        self.updates.append(kwargs)
        return {}


class FakeS3Client:
    def __init__(self):
        self.puts = []

    def put_object(self, **kwargs):
        self.puts.append(kwargs)
        return {}


def load_process_job_module():
    fake_table = FakeTable()
    fake_s3 = FakeS3Client()

    fake_boto3 = types.SimpleNamespace(
        resource=lambda service: types.SimpleNamespace(Table=lambda _name: fake_table),
        client=lambda service: fake_s3,
    )

    previous_boto3 = sys.modules.get("boto3")
    sys.modules["boto3"] = fake_boto3
    os.environ["ARTIFACTS_BUCKET_NAME"] = "artifacts-bucket"
    os.environ["DEMO_SLOW_DELAY_SECONDS"] = "1"
    os.environ["JOBS_TABLE_NAME"] = "jobs-table"

    spec = importlib.util.spec_from_file_location("process_job_app", PROCESS_JOB_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if previous_boto3 is not None:
        sys.modules["boto3"] = previous_boto3
    else:
        sys.modules.pop("boto3", None)

    return module, fake_table, fake_s3


class ProcessJobTests(unittest.TestCase):
    def test_ok_mode_writes_artifact_and_completes_job(self):
        module, table, s3_client = load_process_job_module()

        result = module.handler(
            {
                "Records": [
                    {
                        "body": json.dumps(
                            {"jobId": "job-ok", "mode": "ok", "submittedAt": "now"}
                        )
                    }
                ]
            },
            None,
        )

        self.assertEqual(result["processed"][0]["status"], "COMPLETED")
        self.assertEqual(len(s3_client.puts), 1)
        self.assertEqual(s3_client.puts[0]["Bucket"], "artifacts-bucket")
        self.assertEqual(s3_client.puts[0]["Key"], "artifacts/job-ok.json")
        self.assertEqual(table.updates[0]["ExpressionAttributeValues"][":status"], "PROCESSING")
        self.assertEqual(table.updates[-1]["ExpressionAttributeValues"][":status"], "COMPLETED")

    def test_slow_mode_sleeps_before_writing_artifact(self):
        module, table, s3_client = load_process_job_module()

        with patch.object(module.time, "sleep") as sleep_mock:
            module.handler(
                {
                    "Records": [
                        {
                            "body": json.dumps(
                                {"jobId": "job-slow", "mode": "slow", "submittedAt": "now"}
                            )
                        }
                    ]
                },
                None,
            )

        sleep_mock.assert_called_once_with(1)
        self.assertEqual(len(s3_client.puts), 1)
        self.assertEqual(table.updates[-1]["ExpressionAttributeValues"][":status"], "COMPLETED")

    def test_fail_mode_marks_job_failed_and_raises(self):
        module, table, s3_client = load_process_job_module()

        with self.assertRaisesRegex(RuntimeError, "mode=fail"):
            module.handler(
                {
                    "Records": [
                        {
                            "body": json.dumps(
                                {"jobId": "job-fail", "mode": "fail", "submittedAt": "now"}
                            )
                        }
                    ]
                },
                None,
            )

        self.assertEqual(len(s3_client.puts), 0)
        self.assertEqual(table.updates[-1]["ExpressionAttributeValues"][":status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
