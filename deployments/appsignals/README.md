# Application Signals Deployment Configuration

This deployment configuration uses CloudWatch Application Signals as the backend for the shared demo application.

It keeps the current observability wiring:

- optional `AWS::ApplicationSignals::Discovery`
- `AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument`
- `Tracing: Active`
- `AWSXRayDaemonWriteAccess`
- `CloudWatchLambdaApplicationSignalsExecutionRolePolicy`
- optimized ADOT Lambda layers for Node.js 22 and Python 3.13

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

- stack name: `adot-serverless-demo-appsignals`
- region: `us-east-1`
- ADOT layer ARNs for Node.js 22 and Python 3.13
- `ManageApplicationSignalsDiscovery=false`
- `SlowModeDelaySeconds=6`

## Account-Level Discovery

`AWS::ApplicationSignals::Discovery` is an account-level setup resource. If Application Signals is already enabled in this account and Region, attempting to create it again from this stack will fail with an `already exists in stack` error.

This deployment configuration therefore defaults `ManageApplicationSignalsDiscovery` to `false`.

Use `ManageApplicationSignalsDiscovery=true` only when this stack should perform the one-time account enablement step itself.

Examples:

```bash
sam deploy -t template.yaml \
  --config-file samconfig.toml \
  --guided
```

During the guided deploy, change `ManageApplicationSignalsDiscovery` to `true` only if the account does not already have an `AWS::ApplicationSignals::Discovery` resource in this Region.

## What to Expect

After deployment and the first few invocations:

- CloudWatch Application Signals should discover `demo-api`, `demo-worker`, and `demo-indexer`
- X-Ray service traces should show the API, SQS worker, and downstream dependencies
- trace details should include demo-specific span events for queueing, processing, artifact writes, and indexing
- the shared smoke test should work without changes

Application Signals may take up to about 10 minutes to populate dashboards after the first invoke.

## AWS-Specific Notes

- If this account has never used Application Signals for Lambda, complete the one-time service discovery setup.
- Remove any custom X-Ray SDK instrumentation from the Lambda code if it conflicts with the ADOT layer.
- Keep the stack name lowercase and reasonably short because the stack creates explicit S3 bucket and Lambda function names.

## Smoke Test

Run the shared smoke test with this deployment configuration's stack name:

```bash
./scripts/smoke-test.sh adot-serverless-demo-appsignals
```

## References

- [Enable your applications on Lambda](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-Enable-LambdaMain.html)
- [Monitor application performance with Amazon CloudWatch Application Signals](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-application-signals.html)
- [Visualize Lambda function invocations using AWS X-Ray](https://docs.aws.amazon.com/lambda/latest/dg/services-xray.html)
