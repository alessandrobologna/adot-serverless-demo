# Application Signals Deployment Configuration

This deployment configuration uses CloudWatch Application Signals as the backend for the shared demo application.

It keeps the current observability wiring:

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
- `SlowModeDelaySeconds=6`

## Before You Deploy

This stack does not create the account-level Application Signals discovery resource.

Enable Application Signals for Lambda in this account and Region before you deploy this stack. AWS documents that one-time setup here:

- [Enable your applications on Lambda](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-Enable-LambdaMain.html)
- [AWS::ApplicationSignals::Discovery](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-applicationsignals-discovery.html)

If you prefer infrastructure as code for that one-time enablement step, deploy `AWS::ApplicationSignals::Discovery` separately from this demo stack so it is not coupled to the app lifecycle.

## What to Expect

After deployment and the first few invocations:

- CloudWatch Application Signals should discover four function-scoped services named after the Lambda functions, such as `adot-serverless-demo-appsignals-submit-job` and `adot-serverless-demo-appsignals-process-job`
- X-Ray service traces should show the API, SQS worker, and downstream dependencies
- trace details should include demo-specific span events for queueing, processing, artifact writes, and indexing
- the shared smoke test should work without changes

Application Signals may take up to about 10 minutes to populate dashboards after the first invoke.

## AWS-Specific Notes

- If this account has never used Application Signals for Lambda, complete the one-time enablement step before deploying this stack.
- Remove any custom X-Ray SDK instrumentation from the Lambda code if it conflicts with the ADOT layer.
- Keep the stack name lowercase and reasonably short because the stack creates explicit S3 bucket and Lambda function names.

## Smoke Test

Run the shared smoke test with this deployment configuration's stack name:

```bash
./scripts/smoke-test.sh adot-serverless-demo-appsignals
```

To generate a larger set of successful traces while still verifying the full API -> SQS -> S3 -> indexer path:

```bash
./scripts/smoke-test.sh adot-serverless-demo-appsignals us-east-1 --modes ok --count 100
```

## References

- [Enable your applications on Lambda](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals-Enable-LambdaMain.html)
- [Monitor application performance with Amazon CloudWatch Application Signals](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-application-signals.html)
- [AWS::ApplicationSignals::Discovery](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-applicationsignals-discovery.html)
- [Visualize Lambda function invocations using AWS X-Ray](https://docs.aws.amazon.com/lambda/latest/dg/services-xray.html)
