import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts/check_adot_layers.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("check_adot_layers", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckAdotLayersTests(unittest.TestCase):
    def test_collect_pinned_layer_arns_reads_expected_layers_from_template_defaults(self):
        module = load_module()

        template_text = """
NodeAdotLayerArn:
  Default: arn:aws:lambda:us-east-1:615299751070:layer:AWSOpenTelemetryDistroJs:11
PythonAdotLayerArn:
  Default: arn:aws:lambda:us-east-1:615299751070:layer:AWSOpenTelemetryDistroPython:24
"""

        pinned = module.collect_pinned_layer_arns(template_text, "us-east-1")

        self.assertEqual(
            pinned["AWSOpenTelemetryDistroJs"],
            "arn:aws:lambda:us-east-1:615299751070:layer:AWSOpenTelemetryDistroJs:11",
        )
        self.assertEqual(
            pinned["AWSOpenTelemetryDistroPython"],
            "arn:aws:lambda:us-east-1:615299751070:layer:AWSOpenTelemetryDistroPython:24",
        )

    def test_replace_layer_arns_updates_matching_region_in_samconfig(self):
        module = load_module()

        samconfig_text = """
parameter_overrides = [
    "NodeAdotLayerArn=arn:aws:lambda:us-east-1:615299751070:layer:AWSOpenTelemetryDistroJs:11",
    "PythonAdotLayerArn=arn:aws:lambda:us-east-1:615299751070:layer:AWSOpenTelemetryDistroPython:24",
]
"""

        updated_text, changed = module.replace_layer_arns(
            samconfig_text,
            "us-east-1",
            {
                "AWSOpenTelemetryDistroJs": "arn:aws:lambda:us-east-1:615299751070:layer:AWSOpenTelemetryDistroJs:12",
                "AWSOpenTelemetryDistroPython": "arn:aws:lambda:us-east-1:615299751070:layer:AWSOpenTelemetryDistroPython:24",
            },
        )

        self.assertTrue(changed)
        self.assertIn("AWSOpenTelemetryDistroJs:12", updated_text)
        self.assertIn("AWSOpenTelemetryDistroPython:24", updated_text)

    def test_fetch_latest_layer_info_reads_release_body(self):
        module = load_module()
        target = module.LayerTarget(
            name="AWSOpenTelemetryDistroJs",
            runtime="nodejs22.x",
            release_repo="aws-observability/aws-otel-js-instrumentation",
        )

        with patch.object(
            module,
            "fetch_latest_release_payload",
            return_value={
                "tag_name": "v0.9.0",
                "body": (
                    "|  us-east-1  |  "
                    "arn:aws:lambda:us-east-1:615299751070:layer:AWSOpenTelemetryDistroJs:12  |\n"
                ),
            },
        ) as payload_mock:
            latest_arn, release_tag = module.fetch_latest_layer_info(target, "us-east-1")

        payload_mock.assert_called_once_with("aws-observability/aws-otel-js-instrumentation")
        self.assertEqual(
            latest_arn,
            "arn:aws:lambda:us-east-1:615299751070:layer:AWSOpenTelemetryDistroJs:12",
        )
        self.assertEqual(release_tag, "v0.9.0")


if __name__ == "__main__":
    unittest.main()
