# ADOT Serverless Demo

This repository contains a greenfield AWS SAM application that demonstrates the same Lambda-based document pipeline with two explicit deployment configurations:

- `appsignals` uses CloudWatch Application Signals
- `otel` uses a third-party OpenTelemetry backend over OTLP

Both deployment configurations share:

- a public HTTP API in `nodejs22.x`
- an SQS-driven worker in `python3.13`
- an S3-triggered indexer in `python3.13`
- shared state in DynamoDB and generated artifacts in S3
- custom span events at the main demo milestones so individual traces are easier to inspect

## Relevant AWS Docs

- [Enable your applications on Lambda](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-Enable-LambdaMain.html)
- [Monitor application performance with Amazon CloudWatch Application Signals](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-application-signals.html)
- [AWS Distro for OpenTelemetry Lambda](https://aws-otel.github.io/docs/getting-started/lambda/)
- [AWS Distro for OpenTelemetry Lambda Support For Python](https://aws-otel.github.io/docs/getting-started/lambda/lambda-python/)
- [AWS Distro for OpenTelemetry Lambda Support For JavaScript](https://aws-otel.github.io/docs/getting-started/lambda/lambda-js/)
- [AWS::ApplicationSignals::Discovery](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-applicationsignals-discovery.html)

## Architecture

The demo flows through three phases: request intake, worker processing, and artifact indexing.

### Request Intake

The public API accepts the request, records the initial job state in DynamoDB, and enqueues background work in SQS.

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./svgs/readme-1-dark.svg">
  <img src="./svgs/readme-1-light.svg" alt="Architecture diagram">
</picture>
</div>

<details data-mermint-source="true">
  <summary>Mermaid source</summary>

```mermaid
---
config:
  theme: base
  look: handDrawn
  themeVariables:
    lineColor: "#7d8593"
  architecture:
    iconSize: 64
    padding: 48
    fontSize: 16
x-mermint:
  rough:
    fillStyle: solid
---
architecture-beta
  group api_group(aws:aws-api-gateway)[API]
  service gateway(aws:aws-api-gateway)[Gateway] in api_group

  group submit_group(aws:aws-lambda)[Submit]
  service submit(aws:aws-lambda)[Lambda] in submit_group

  group state(aws:dynamodb)[State]
  service jobs(aws:dynamodb)[Jobs] in state

  group messaging(aws:simple-queue-service)[Messaging]
  service queue(aws:simple-queue-service)[Queue] in messaging

  gateway:R --> L:submit
  submit:B --> T:jobs
  submit:R --> L:queue
```

</details>

### Worker Processing

The worker consumes queue messages, updates job state, writes artifacts to S3, and sends failed messages to the DLQ.

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./svgs/readme-2-dark.svg">
  <img src="./svgs/readme-2-light.svg" alt="Architecture diagram">
</picture>
</div>

<details data-mermint-source="true">
  <summary>Mermaid source</summary>

```mermaid
---
config:
  theme: base
  look: handDrawn
  themeVariables:
    lineColor: "#7d8593"
  architecture:
    iconSize: 64
    padding: 48
    fontSize: 16
x-mermint:
  rough:
    fillStyle: solid
---
architecture-beta
  group messaging(aws:simple-queue-service)[Messaging]
  service queue(aws:simple-queue-service)[Queue] in messaging
  service dlq(aws:simple-queue-service)[DLQ] in messaging

  group worker_group(aws:aws-lambda)[Worker]
  service worker(aws:aws-lambda)[Lambda] in worker_group

  group state(aws:dynamodb)[State]
  service jobs(aws:dynamodb)[Jobs] in state

  group storage(aws:simple-storage-service)[Artifacts]
  service bucket(aws:simple-storage-service)[Bucket] in storage

  queue:R --> L:worker
  queue:B --> T:dlq
  worker:B --> T:jobs
  worker:R --> L:bucket
```

</details>

### Artifact Indexing

The indexer reacts to new S3 objects and writes the artifact metadata back to the shared jobs table.

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./svgs/readme-3-dark.svg">
  <img src="./svgs/readme-3-light.svg" alt="Architecture diagram">
</picture>
</div>

<details data-mermint-source="true">
  <summary>Mermaid source</summary>

```mermaid
---
config:
  theme: base
  look: handDrawn
  themeVariables:
    lineColor: "#7d8593"
  architecture:
    iconSize: 64
    padding: 48
    fontSize: 16
x-mermint:
  rough:
    fillStyle: solid
---
architecture-beta
  group storage(aws:simple-storage-service)[Artifacts]
  service bucket(aws:simple-storage-service)[Bucket] in storage

  group indexer_group(aws:aws-lambda)[Indexer]
  service indexer(aws:aws-lambda)[Lambda] in indexer_group

  group state(aws:dynamodb)[State]
  service jobs(aws:dynamodb)[Jobs] in state

  bucket:R --> L:indexer
  indexer:B --> T:jobs
```

</details>

Each Lambda function is instrumented with ADOT. Both deployment configurations share:

- the runtime-specific AWS Distro for OpenTelemetry (ADOT) Lambda layer
- `AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument`

The `appsignals` deployment additionally uses:

- a one-time Application Signals enablement step in the target account and Region
- `CloudWatchLambdaApplicationSignalsExecutionRolePolicy`
- `AWSXRayDaemonWriteAccess`

The template is intentionally pinned to `us-east-1`, including the Node.js and Python ADOT layer ARNs.

> [!NOTE]
> As of March 7, 2026, the ADOT Python Lambda layer docs list support through Python 3.13, and the Lambda Application Signals runtime list also stops at Python 3.13. `python3.14` is not yet supported by the ADOT Python Lambda layer for this integration, so this demo pins the Python functions to `python3.13`.

## Deployment Configurations

Choose one deployment entrypoint:

- [Application Signals deployment configuration](deployments/appsignals/README.md)
  This configuration assumes Application Signals has already been enabled in the target account and Region, and links to the AWS setup documentation.
- [OTel deployment configuration](deployments/otel/README.md)
  This guide documents an important Lambda-specific OTLP detail: the optimized ADOT Lambda layers need `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, not just the generic OTLP endpoint variable, to avoid the Lambda UDP fallback path.

Canonical commands:

```bash
cd deployments/appsignals
sam build -t template.yaml --config-file samconfig.toml
sam deploy -t template.yaml --config-file samconfig.toml --guided
```

```bash
cd deployments/otel
sam build -t template.yaml --config-file samconfig.toml
sam deploy -t template.yaml --config-file samconfig.toml --guided
```

## Prerequisites

- AWS CLI configured with credentials
- AWS SAM CLI 1.154.0 or newer
- Node.js 22 or newer with npm
- Python 3.12 or newer for local tests, smoke scripts, and helper scripts
- `curl`

## Local Verification

Run the unit tests:

```bash
make test
```

Equivalent `just` command:

```bash
just test
```

> [!NOTE]
> `src/node-api/package-lock.json` is intentionally not committed. This repository is a demo/reference for the SAM architecture and ADOT/Application Signals wiring, not a pinned production dependency baseline.

You can also inspect sample invoke payloads in [`events/http-submit-ok.json`](events/http-submit-ok.json), [`events/sqs-work.json`](events/sqs-work.json), and [`events/s3-artifact.json`](events/s3-artifact.json).

## ADOT Layer Maintenance

AWS Lambda layer references are versioned ARNs, so both deployment configurations pin exact ADOT layer versions in their own templates and configs.

There is no native SAM property for "latest ADOT layer version", so this repo provides a script to check for drift against the latest official AWS Observability release metadata for the `AWSOpenTelemetryDistro*` layers.

Check whether a newer ADOT layer version has been published in `us-east-1`:

```bash
make check-adot-layers
```

Equivalent `just` command:

```bash
just check-adot-layers
```

Update both deployment configuration templates and their local `samconfig.toml` overrides to the latest published ADOT layer versions for the region:

```bash
make update-adot-layers
```

Equivalent `just` command:

```bash
just update-adot-layers
```

The underlying script also supports explicit flags for each deployment configuration:

- `--fail-on-drift` checks the pinned layer ARNs and exits non-zero when either deployment configuration is behind the latest published ADOT layer version. This is the useful mode for CI or local verification.
- `--write-files` rewrites the target template and matching `samconfig.toml` to the latest published ADOT layer ARNs for the requested region.

```bash
python3 scripts/check_adot_layers.py --template deployments/appsignals/template.yaml --samconfig deployments/appsignals/samconfig.toml --region us-east-1 --fail-on-drift
python3 scripts/check_adot_layers.py --template deployments/otel/template.yaml --samconfig deployments/otel/samconfig.toml --region us-east-1 --write-files
```

## Post-Deploy Smoke Test

By default, the smoke script submits one `ok`, one `slow`, and one `fail` job, then verifies:

- `ok` reaches `COMPLETED`
- `slow` reaches `COMPLETED`
- successful jobs have artifacts in S3 and `artifactIndexedAt`, so the S3-triggered indexer path has completed
- `fail` reaches `FAILED`
- the worker DLQ depth increases

The handlers also emit demo-specific span events such as `demo.job.enqueued`, `demo.job.processing.started`, `demo.artifact.written`, and `demo.artifact.indexed`, which makes it easier to verify the flow inside a single trace.

Run it with:

```bash
./scripts/smoke-test.sh <stack-name> [aws-region] [--count N] [--modes ok,slow,fail]
```

`--count` applies per mode. For example, `--modes ok --count 100` submits 100 successful jobs.

Examples:

```bash
./scripts/smoke-test.sh adot-serverless-demo-appsignals
./scripts/smoke-test.sh adot-serverless-demo-otel
./scripts/smoke-test.sh adot-serverless-demo-appsignals us-east-1 --modes ok --count 100
```

## Cleanup

The artifacts bucket is intentionally left as a normal bucket. Empty it before deleting the stack:

```bash
aws s3 rm s3://<artifacts-bucket-name> --recursive
sam delete --stack-name <stack-name>
```
