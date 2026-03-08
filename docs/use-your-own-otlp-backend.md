# Use Your Own OTLP Backend

This repository is currently wired for CloudWatch Application Signals. The Lambda functions use the optimized ADOT Lambda layers, `AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument`, `CloudWatchLambdaApplicationSignalsExecutionRolePolicy`, and `Tracing: Active`.

This guide explains what changes when the telemetry backend is a custom OTLP endpoint instead of CloudWatch Application Signals.

## Scope

This guide focuses on Lambda auto-instrumentation through ADOT layers.

There are two distinct paths:

1. Keep the optimized ADOT Lambda layers and point trace export at a custom OTLP endpoint with standard OpenTelemetry environment variables.
2. Switch to the legacy collector-backed ADOT Lambda layers when a custom collector pipeline is required.

The first path is the smaller change. The second path is the more flexible change.

## Current Baseline in This Repo

The current SAM template in [template.yaml](/Users/alessandro/git/adot-serverless-demo/template.yaml) does the following:

- Enables `AWS::ApplicationSignals::Discovery`
- Attaches the optimized `AWSOpenTelemetryDistroJs` and `AWSOpenTelemetryDistroPython` layers
- Sets `AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument`
- Sets `OTEL_SERVICE_NAME` per service group
- Enables `Tracing: Active`
- Attaches `AWSXRayDaemonWriteAccess`
- Attaches `arn:aws:iam::aws:policy/CloudWatchLambdaApplicationSignalsExecutionRolePolicy`

That combination is correct for CloudWatch Application Signals. It is not the correct final state for a pure bring-your-own OTLP backend setup.

## Decision Point

Use the optimized layers first if the goal is:

- traces only
- one OTLP traces endpoint
- simple header-based authentication
- minimal changes to the current demo

Use the legacy collector-backed layers if the goal is:

- multiple pipelines or exporters
- collector processors such as `batch`
- more complex auth or routing
- explicit control over traces, metrics, and logs in one collector config

> [!IMPORTANT]
> The ADOT Lambda docs now describe the collector-backed layers as the legacy path. They are still the right tool when the endpoint is not CloudWatch and a custom collector pipeline is required.

## Option 1: Keep the Optimized ADOT Layers

This is the smallest change from the current repo.

### Required environment changes

Add these environment variables to the instrumented functions:

```yaml
Environment:
  Variables:
    AWS_LAMBDA_EXEC_WRAPPER: /opt/otel-instrument
    OTEL_AWS_APPLICATION_SIGNALS_ENABLED: "false"
    OTEL_SERVICE_NAME: demo-api
    OTEL_TRACES_EXPORTER: otlp
    OTEL_EXPORTER_OTLP_TRACES_PROTOCOL: http/protobuf
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: https://otlp.example.com/v1/traces
    OTEL_EXPORTER_OTLP_TRACES_HEADERS: authorization=Bearer ${TOKEN}
```

These settings do three things:

- keep Lambda auto-instrumentation enabled
- disable the Application Signals backend behavior
- send traces to a custom OTLP endpoint

### Endpoint semantics

OpenTelemetry has two endpoint styles, and they behave differently:

- `OTEL_EXPORTER_OTLP_ENDPOINT` is a base URL. The SDK appends `/v1/traces`, `/v1/metrics`, and `/v1/logs`.
- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` is used as-is. Include the full traces path when using it.

For example:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp.example.com
```

sends traces to `https://otlp.example.com/v1/traces`.

By contrast:

```bash
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://otlp.example.com/v1/traces
```

must already include the full path.

### Additional standard OpenTelemetry knobs

These variables are useful when the backend needs more than just an endpoint:

- `OTEL_EXPORTER_OTLP_TRACES_HEADERS`
- `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL`
- `OTEL_EXPORTER_OTLP_TRACES_TIMEOUT`
- `OTEL_EXPORTER_OTLP_TRACES_COMPRESSION`
- `OTEL_EXPORTER_OTLP_TRACES_CERTIFICATE`
- `OTEL_EXPORTER_OTLP_TRACES_CLIENT_CERTIFICATE`
- `OTEL_EXPORTER_OTLP_TRACES_CLIENT_KEY`

`http/protobuf` is the safest starting point for managed OTLP backends. Switch only if the backend explicitly requires gRPC or JSON.

### IAM and tracing changes

If the repo moves away from Application Signals completely, these current settings should be revisited:

- `AWS::ApplicationSignals::Discovery`
- `CloudWatchLambdaApplicationSignalsExecutionRolePolicy`

The managed policy only grants `xray:PutTraceSegments` plus writes to `/aws/application-signals/data`. It is specific to the CloudWatch Application Signals path.

`Tracing: Active` is a separate choice:

- Keep it if Lambda service traces in X-Ray are still wanted.
- Remove it if the goal is a pure custom-OTLP path with no X-Ray service traces.

If `Tracing: Active` remains enabled, keep `AWSXRayDaemonWriteAccess`. If it is removed, that policy can usually be removed too.

### Suggested repo-level change set

For this repository, the minimal starting diff would be:

1. Add parameters for `OtlpTracesEndpoint` and `OtlpTracesHeaders`.
2. Set `OTEL_AWS_APPLICATION_SIGNALS_ENABLED=false` in `Globals.Function.Environment.Variables`.
3. Set `OTEL_TRACES_EXPORTER=otlp`.
4. Set `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf`.
5. Set `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` from a parameter.
6. Set `OTEL_EXPORTER_OTLP_TRACES_HEADERS` from a parameter.
7. Remove `ApplicationSignalsDiscovery` and `CloudWatchLambdaApplicationSignalsExecutionRolePolicy` once CloudWatch Application Signals is no longer needed.

## Option 2: Keep the Optimized ADOT Layers and Add the Upstream OTel Collector Layer

Use this path when the optimized ADOT instrumentation layers are still the right fit, but a collector pipeline is needed for routing, processors, or multi-signal export.

This is the cleaner advanced path for this repository.

The reasoning is:

- the ADOT Lambda docs describe the current `AWSOpenTelemetryDistro*` layers as optimized layers that no longer require a dedicated collector, and they allow custom OTLP exporter settings
- the upstream OpenTelemetry Lambda docs publish the Collector as a standalone Lambda layer that is meant to be added after instrumentation

Taken together, it makes more sense to keep the optimized ADOT instrumentation layers and add the standalone upstream Collector layer than to switch this repo back to the legacy AWS collector-backed layer families.

> [!NOTE]
> This is a compositional recommendation inferred from the current ADOT and upstream OpenTelemetry docs. AWS does not publish it as a single turnkey recipe for this exact combination.

### Why use this path

This path keeps the current instrumentation layer family and adds a real collector pipeline. That matters when the setup needs:

- `processors`
- multiple exporters
- signal-specific pipelines
- collector extensions
- custom retry and batching behavior

### What changes in the function configuration

Keep the current optimized ADOT instrumentation layer and add the upstream Collector Lambda layer ARN for the same Region and architecture.

Then point the function's OTLP exporter to the local collector and provide a collector config:

```yaml
Environment:
  Variables:
    AWS_LAMBDA_EXEC_WRAPPER: /opt/otel-instrument
    OTEL_AWS_APPLICATION_SIGNALS_ENABLED: "false"
    OTEL_TRACES_EXPORTER: otlp
    OTEL_EXPORTER_OTLP_TRACES_PROTOCOL: http/protobuf
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: http://localhost:4318/v1/traces
    OPENTELEMETRY_COLLECTOR_CONFIG_URI: /var/task/collector.yaml
```

If the setup later adds logs or metrics, use the corresponding OTLP exporter variables and route them through the same local collector.

### Minimal collector example for a custom traces backend

```yaml
receivers:
  otlp:
    protocols:
      grpc:
      http:

processors:
  batch:

exporters:
  otlphttp:
    endpoint: https://otlp.example.com
    headers:
      authorization: Bearer ${env:OTLP_AUTH_TOKEN}

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp]
```

This example uses the standard OTLP receiver and the `otlphttpexporter`.

### What changes in the repo

For this repository, this path usually means:

1. Keep `NodeAdotLayerArn` and `PythonAdotLayerArn` as the optimized ADOT instrumentation layers.
2. Add a new parameter for the upstream Collector Lambda layer ARN.
3. Add `collector.yaml` to the deployment package.
4. Set `OPENTELEMETRY_COLLECTOR_CONFIG_URI`.
5. Point the OTLP traces endpoint at `http://localhost:4318/v1/traces`.
6. Remove `ApplicationSignalsDiscovery`.
7. Remove `CloudWatchLambdaApplicationSignalsExecutionRolePolicy`.
8. Keep or remove `Tracing: Active` based on whether X-Ray Lambda service traces are still wanted.

### Fallback: AWS legacy collector-backed layers

AWS still publishes the older collector-backed `aws-otel-...` Lambda layer families and documents custom collector configuration for them.

The ADOT docs explicitly keep that path for non-CloudWatch endpoints. This guide treats it as a fallback because the upstream collector layer composes more cleanly with the optimized `AWSOpenTelemetryDistro*` instrumentation layers that this repository already uses.

## Metrics and Logs

AWS explicitly documents custom OTLP export on the optimized Lambda path for traces. The optimized Lambda docs still focus on CloudWatch-specific flows for metrics and logs.

Because of that, a safe rule is:

- traces only: start with the optimized layers and OTLP trace env vars
- traces, metrics, and logs with a custom backend: prefer the standalone collector layer path

This is partly an inference from the current docs. The ADOT Lambda docs clearly describe a custom OTLP traces path on the optimized layers, while the upstream OpenTelemetry Lambda docs describe the Collector as a standalone layer that can be used alongside instrumentation layers.

## Recommended Migration Order

1. Repoint traces first.
2. Validate service naming through `OTEL_SERVICE_NAME`.
3. Validate async behavior across API Gateway, SQS, Lambda, DynamoDB, and S3 in the target backend.
4. Decide whether `Tracing: Active` still adds value.
5. Only then remove the Application Signals resources and IAM policy.
6. Move to the standalone collector layer path only if traces-only OTLP export is not enough.

## References

- [Enable your applications on Lambda](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-Enable-LambdaMain.html)
- [Monitor application performance with Amazon CloudWatch Application Signals](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-application-signals.html)
- [CloudWatchLambdaApplicationSignalsExecutionRolePolicy](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/CloudWatchLambdaApplicationSignalsExecutionRolePolicy.html)
- [Visualize Lambda function invocations using AWS X-Ray](https://docs.aws.amazon.com/lambda/latest/dg/services-xray.html)
- [AWS Distro for OpenTelemetry Lambda](https://aws-otel.github.io/docs/getting-started/lambda/)
- [Custom Configuration for ADOT Collector on Lambda](https://aws-otel.github.io/docs/getting-started/lambda/lambda-custom-configuration/)
- [Lambda Collector Configuration](https://opentelemetry.io/docs/platforms/faas/lambda-collector/)
- [Functions as a Service](https://opentelemetry.io/docs/platforms/faas/)
- [aws-otel-lambda supported components](https://github.com/aws-observability/aws-otel-lambda/blob/main/README.md)
- [OpenTelemetry Protocol Exporter specification](https://opentelemetry.io/docs/specs/otel/protocol/exporter/)
