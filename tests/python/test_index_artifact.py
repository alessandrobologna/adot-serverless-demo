import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path


INDEX_ARTIFACT_PATH = (
    Path(__file__).resolve().parents[2] / "src/python-workers/index_artifact/app.py"
)


class FakeTable:
    def __init__(self):
        self.updates = []

    def update_item(self, **kwargs):
        self.updates.append(kwargs)
        return {}


class FakeS3Client:
    def __init__(self):
        self.heads = []

    def head_object(self, **kwargs):
        self.heads.append(kwargs)
        return {
            "ContentLength": 128,
            "ContentType": "application/json",
        }


def load_index_artifact_module():
    fake_table = FakeTable()
    fake_s3 = FakeS3Client()

    fake_boto3 = types.SimpleNamespace(
        resource=lambda service: types.SimpleNamespace(Table=lambda _name: fake_table),
        client=lambda service: fake_s3,
    )

    previous_boto3 = sys.modules.get("boto3")
    sys.modules["boto3"] = fake_boto3
    os.environ["JOBS_TABLE_NAME"] = "jobs-table"

    spec = importlib.util.spec_from_file_location("index_artifact_app", INDEX_ARTIFACT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if previous_boto3 is not None:
        sys.modules["boto3"] = previous_boto3
    else:
        sys.modules.pop("boto3", None)

    return module, fake_table, fake_s3


class IndexArtifactTests(unittest.TestCase):
    def test_indexer_updates_table_from_s3_metadata(self):
        module, table, s3_client = load_index_artifact_module()

        result = module.handler(
            {
                "Records": [
                    {
                        "s3": {
                            "bucket": {"name": "artifacts-bucket"},
                            "object": {"key": "artifacts/job-123.json"},
                        }
                    }
                ]
            },
            None,
        )

        self.assertEqual(result["indexed"][0]["jobId"], "job-123")
        self.assertEqual(s3_client.heads[0]["Bucket"], "artifacts-bucket")
        self.assertEqual(s3_client.heads[0]["Key"], "artifacts/job-123.json")
        self.assertEqual(table.updates[0]["Key"]["jobId"], "job-123")
        self.assertEqual(table.updates[0]["ExpressionAttributeValues"][":artifactSize"], 128)


if __name__ == "__main__":
    unittest.main()
