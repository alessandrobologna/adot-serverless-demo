#!/usr/bin/env python3

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


LAYER_ARN_RE = re.compile(
    r"arn:aws:lambda:(?P<region>[^:]+):(?P<account>\d+):layer:(?P<name>[^:]+):(?P<version>\d+)"
)


@dataclass(frozen=True)
class LayerTarget:
    name: str
    runtime: str
    release_repo: str


LAYER_TARGETS = (
    LayerTarget(
        name="AWSOpenTelemetryDistroJs",
        runtime="nodejs22.x",
        release_repo="aws-observability/aws-otel-js-instrumentation",
    ),
    LayerTarget(
        name="AWSOpenTelemetryDistroPython",
        runtime="python3.13",
        release_repo="aws-observability/aws-otel-python-instrumentation",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether newer ADOT Lambda layer versions are available."
    )
    parser.add_argument(
        "--template",
        default="deployments/appsignals/template.yaml",
        help="Path to the SAM template to inspect. Default: deployments/appsignals/template.yaml",
    )
    parser.add_argument(
        "--samconfig",
        default="deployments/appsignals/samconfig.toml",
        help="Path to the samconfig file to inspect and update when present. Default: deployments/appsignals/samconfig.toml",
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region to query. Default: us-east-1",
    )
    parser.add_argument(
        "--write-files",
        action="store_true",
        help="Rewrite template defaults and samconfig overrides with the latest published layer ARNs.",
    )
    parser.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="Exit with status 1 when the template or samconfig is not using the latest layer versions.",
    )
    return parser.parse_args()


def load_text(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8")


def collect_pinned_layer_arns(template_text: str, region: str) -> dict[str, str]:
    pinned_arns: dict[str, str] = {}
    expected_layer_names = {target.name for target in LAYER_TARGETS}

    for match in LAYER_ARN_RE.finditer(template_text):
        layer_region = match.group("region")
        layer_name = match.group("name")
        layer_arn = match.group(0)

        if layer_region != region:
            continue

        if layer_name not in expected_layer_names:
            continue

        existing_arn = pinned_arns.get(layer_name)
        if existing_arn is not None and existing_arn != layer_arn:
            raise ValueError(
                f"Template contains multiple pinned ARNs for layer {layer_name} in {region}: "
                f"{existing_arn} and {layer_arn}"
            )

        pinned_arns[layer_name] = layer_arn

    missing_layers = [target.name for target in LAYER_TARGETS if target.name not in pinned_arns]
    if missing_layers:
        missing = ", ".join(missing_layers)
        raise ValueError(f"Template does not pin all expected ADOT layers for {region}: {missing}")

    return pinned_arns


def fetch_latest_release_payload(repo: str) -> dict:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "adot-serverless-demo-layer-checker",
        },
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Failed to fetch the latest release for {repo}: HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Failed to fetch the latest release for {repo}: {exc.reason}"
        )


def fetch_latest_layer_info(target: LayerTarget, region: str) -> tuple[str, str]:
    payload = fetch_latest_release_payload(target.release_repo)
    release_tag = payload["tag_name"]
    release_body = payload.get("body", "")
    region_pattern = re.compile(
        rf"\|\s*{re.escape(region)}\s*\|\s*(arn:aws:lambda:{re.escape(region)}:[^|\s]+)\s*\|"
    )
    match = region_pattern.search(release_body)
    if match is None:
        raise RuntimeError(
            f"The latest release for {target.release_repo} ({release_tag}) does not list "
            f"an ARN for region {region}."
        )

    latest_arn = match.group(1)
    if f":layer:{target.name}:" not in latest_arn:
        raise RuntimeError(
            f"The latest release for {target.release_repo} ({release_tag}) returned "
            f"an ARN for a different layer: {latest_arn}"
        )

    return latest_arn, release_tag


def replace_layer_arns(
    template_text: str, region: str, latest_arns: dict[str, str]
) -> tuple[str, bool]:
    changed = False

    def replacement(match: re.Match[str]) -> str:
        nonlocal changed

        layer_region = match.group("region")
        layer_name = match.group("name")

        if layer_region != region or layer_name not in latest_arns:
            return match.group(0)

        latest_arn = latest_arns[layer_name]
        if match.group(0) != latest_arn:
            changed = True
        return latest_arn

    updated_text = LAYER_ARN_RE.sub(replacement, template_text)
    return updated_text, changed


def describe_layer_status(
    layer_name: str, current_arn: str, latest_arn: str, release_repo: str, release_tag: str
) -> str:
    current_version = current_arn.rsplit(":", 1)[-1]
    latest_version = latest_arn.rsplit(":", 1)[-1]
    status = "up to date" if current_arn == latest_arn else "update available"
    return (
        f"{layer_name}: {status}\n"
        f"  current: {current_arn}\n"
        f"  latest:  {latest_arn}\n"
        f"  version: {current_version} -> {latest_version}\n"
        f"  source:  {release_repo}@{release_tag}"
    )


def main() -> int:
    args = parse_args()
    template_path = Path(args.template)
    template_text = load_text(template_path)
    template_arns = collect_pinned_layer_arns(template_text, args.region)
    samconfig_path = Path(args.samconfig)
    samconfig_text = None
    samconfig_arns = None

    if samconfig_path.exists():
        samconfig_text = load_text(samconfig_path)
        samconfig_arns = collect_pinned_layer_arns(samconfig_text, args.region)

    latest_layer_info = {
        target.name: fetch_latest_layer_info(target, args.region) for target in LAYER_TARGETS
    }
    latest_arns = {
        layer_name: layer_info[0] for layer_name, layer_info in latest_layer_info.items()
    }

    drift_detected = False
    for target in LAYER_TARGETS:
        current_arn = template_arns[target.name]
        latest_arn, release_tag = latest_layer_info[target.name]
        if current_arn != latest_arn:
            drift_detected = True
        print(
            describe_layer_status(
                target.name,
                current_arn,
                latest_arn,
                target.release_repo,
                release_tag,
            )
        )
        if samconfig_arns is not None:
            samconfig_arn = samconfig_arns[target.name]
            if samconfig_arn != current_arn:
                drift_detected = True
                print(
                    f"  samconfig: {samconfig_arn}\n"
                    f"  warning: template default and samconfig override differ"
                )
            elif samconfig_arn != latest_arn:
                drift_detected = True

    if args.write_files:
        updated_text, changed = replace_layer_arns(template_text, args.region, latest_arns)
        if changed:
            template_path.write_text(updated_text, encoding="utf-8")
            print(f"\nUpdated {template_path} with the latest ADOT layer ARNs for {args.region}.")
        else:
            print(f"\nNo template changes were required for {args.region}.")
        if samconfig_text is not None:
            updated_samconfig_text, samconfig_changed = replace_layer_arns(
                samconfig_text,
                args.region,
                latest_arns,
            )
            if samconfig_changed:
                samconfig_path.write_text(updated_samconfig_text, encoding="utf-8")
                print(
                    f"Updated {samconfig_path} with the latest ADOT layer ARNs for {args.region}."
                )
            else:
                print(f"No samconfig changes were required for {args.region}.")

    if args.fail_on_drift and drift_detected:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
