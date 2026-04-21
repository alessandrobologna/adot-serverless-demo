# OTel Deployment Configuration

This deployment configuration sends traces from the shared demo application directly to a third-party OpenTelemetry backend over OTLP HTTP/protobuf.

It keeps the optimized ADOT Lambda layers and removes the CloudWatch Application Signals and X-Ray-specific wiring.

## What Changes in This Deployment Configuration

This deployment configuration keeps:

- optimized ADOT Lambda layers for Node.js 22 and Python 3.13
- `AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument`
- the shared Lambda handlers, event sources, and stack outputs
- function-scoped `OTEL_SERVICE_NAME` values that match each Lambda function name

This deployment configuration removes:

- `CloudWatchLambdaApplicationSignalsExecutionRolePolicy`
- `AWSXRayDaemonWriteAccess`
- `Tracing: Active`

This deployment configuration adds direct OTLP trace export through environment variables:

- `OTEL_AWS_APPLICATION_SIGNALS_ENABLED=false`
- `OTEL_PROPAGATORS=tracecontext`
- `OTEL_TRACES_EXPORTER=otlp`
- `OTEL_TRACES_SAMPLER=always_on`
- `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf`
- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`
- `OTEL_EXPORTER_OTLP_TRACES_HEADERS`

The endpoint and headers values are resolved from an AWS Secrets Manager `SecretString` JSON object at deploy time.

## Build and Deploy

Build from this directory:

```bash
sam build -t template.yaml --config-file samconfig.toml
```

Deploy interactively:

```bash
sam deploy -t template.yaml --config-file samconfig.toml --guided
```

Committed defaults:

- stack name: `adot-serverless-demo-otel`
- region: `us-east-1`
- ADOT layer ARNs for Node.js 22 and Python 3.13
- `SlowModeDelaySeconds=6`
- backend secret name: `adot-serverless-demo-otel-backend`
- backend config version: `2026-03-19-1`

## Required Configuration

Create a Secrets Manager secret before the first deploy. The template expects a JSON `SecretString` with these keys:

- `endpoint`: base OTLP endpoint URL with a trailing slash, for example `https://otlp.example.com/`
- `auth`: OTLP headers string, for example `authorization=Bearer token`. If the backend does not require headers, set this key to an empty string.
- `name`: optional metadata field for the backend or platform name. The template does not currently read it.

Example secret payload:

```json
{
  "name": "platform-name",
  "endpoint": "https://otlp.example.com/",
  "auth": "authorization=Bearer <token>"
}
```

Create the secret from the CLI with a file-backed payload:

```bash
cat > otel-backend-secret.json <<'EOF'
{
  "name": "platform-name",
  "endpoint": "https://otlp.example.com/",
  "auth": "authorization=Bearer <token>"
}
EOF

aws secretsmanager create-secret \
  --name adot-serverless-demo-otel-backend \
  --secret-string file://otel-backend-secret.json \
  --region us-east-1
```

If the secret already exists, update it instead:

```bash
aws secretsmanager put-secret-value \
  --secret-id adot-serverless-demo-otel-backend \
  --secret-string file://otel-backend-secret.json \
  --region us-east-1
```

Then either keep the committed secret name or override `OtelBackendSecretName` during `sam deploy --guided`.

Examples:

```bash
sam deploy -t template.yaml \
  --config-file samconfig.toml \
  --guided
```

During the guided deploy, change `OtelBackendSecretName` if you want to use a different secret name or ARN.

CloudFormation dynamic references can be used in resource properties, including Lambda environment variables, but AWS documents that the resolved value may still show up in the target service. In this deployment configuration, the secret is resolved into Lambda environment variables, so treat the function configuration as sensitive.

## Refreshing Secret Changes

CloudFormation resolves the Secrets Manager dynamic references during stack operations, but it does not automatically notice later secret value changes.

This deployment configuration includes a dedicated `OtelBackendConfigVersion` parameter that is copied into a harmless Lambda environment variable named `OTEL_BACKEND_CONFIG_VERSION`. Bump that parameter whenever you update the secret so the Lambda resources change and CloudFormation re-resolves the OTLP endpoint and header values.

For example, after changing the secret:

```toml
parameter_overrides = [
    "SlowModeDelaySeconds=6",
    "NodeAdotLayerArn=arn:aws:lambda:us-east-1:615299751070:layer:AWSOpenTelemetryDistroJs:12",
    "PythonAdotLayerArn=arn:aws:lambda:us-east-1:615299751070:layer:AWSOpenTelemetryDistroPython:24",
    "OtelBackendSecretName=adot-serverless-demo-otel-backend",
    "OtelBackendConfigVersion=2026-03-19-2",
]
```

Then run:

```bash
sam deploy -t template.yaml --config-file samconfig.toml
```

## Expectations

This deployment configuration is meant for third-party OpenTelemetry backends.

It does not configure:

- CloudWatch Application Signals dashboards
- X-Ray Lambda service traces

The shared smoke test still exercises the same application flow, but any observability validation happens in the external backend instead of CloudWatch.

Trace details should also include demo-specific span events for queueing, processing, artifact writes, and indexing.

## OTLP Endpoint Semantics

This template derives `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` from the secret's base `endpoint` value by appending `v1/traces`. Keep the secret value as a base OTLP URL with a trailing slash, for example `https://otlp.example.com/`.

This deployment configuration uses the trace-specific endpoint variable because the optimized ADOT Lambda layers check `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` in Lambda when deciding whether to stay on OTLP export or fall back to the Lambda UDP path.

In practice, this means:

- setting only the generic `OTEL_EXPORTER_OTLP_ENDPOINT` is not sufficient for this Lambda deployment configuration
- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` must be present to keep the optimized Node.js and Python Lambda layers on the OTLP export path
- this repo intentionally sets the trace-specific endpoint and headers env vars for that reason

During live validation of this repo, the Node Lambda logs showed `Detected AWS Lambda environment and enabling UDPSpanExporter` when only the generic OTLP endpoint variable was set. After switching to `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, the same logs started showing `OTLPExportDelegate items to be sent [`, which confirmed the exporter path changed from the Lambda UDP fallback to OTLP. The temporary `OTEL_LOG_LEVEL=debug` setting used for that investigation has been removed from the committed deployment configuration.

## Smoke Test

Run the shared smoke test with this deployment configuration's stack name:

```bash
./scripts/smoke-test.sh adot-serverless-demo-otel
```

To generate a larger set of successful traces for the external backend while still verifying the full API -> SQS -> S3 -> indexer path:

```bash
./scripts/smoke-test.sh adot-serverless-demo-otel us-east-1 --modes ok --count 100
```

## References

- [Get a secret or secret value from Secrets Manager](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references-secretsmanager.html)
- [Create an AWS Secrets Manager secret](https://docs.aws.amazon.com/secretsmanager/latest/userguide/create_secret.html)
- [AWS Distro for OpenTelemetry Lambda](https://aws-otel.github.io/docs/getting-started/lambda/)
- [OpenTelemetry Protocol Exporter specification](https://opentelemetry.io/docs/specs/otel/protocol/exporter/)
- [OpenTelemetry Protocol (OTLP) Endpoint](https://docs.aws.amazon.com/xray/latest/devguide/xray-opentelemetry.html)
