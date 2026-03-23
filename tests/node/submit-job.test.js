"use strict";

const assert = require("node:assert/strict");
const { afterEach, test, mock } = require("node:test");
const { trace } = require("@opentelemetry/api");
const { DynamoDBDocumentClient, PutCommand } = require("@aws-sdk/lib-dynamodb");
const { SQSClient, SendMessageCommand } = require("@aws-sdk/client-sqs");

const submitJob = require("../../src/node-api/submit-job/app");

afterEach(() => {
  mock.restoreAll();
  delete process.env.WORK_QUEUE_URL;
  delete process.env.JOBS_TABLE_NAME;
});

test("POST /jobs queues work and persists the job", async () => {
  process.env.JOBS_TABLE_NAME = "jobs-table";
  process.env.WORK_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/123/demo";

  const commands = [];
  const events = [];
  mock.method(DynamoDBDocumentClient.prototype, "send", async (command) => {
    commands.push(command);
    return {};
  });
  mock.method(SQSClient.prototype, "send", async (command) => {
    commands.push(command);
    return { MessageId: "message-1" };
  });
  mock.method(trace, "getActiveSpan", () => ({
    addEvent(name, attributes) {
      events.push({ attributes, name });
    },
  }));

  const response = await submitJob.handler({
    body: JSON.stringify({ mode: "ok", payload: { orderId: "1234" } }),
    isBase64Encoded: false,
  });

  assert.equal(response.statusCode, 202);
  const body = JSON.parse(response.body);
  assert.equal(body.mode, "ok");
  assert.equal(body.status, "QUEUED");
  assert.match(body.jobId, /^[0-9a-f-]{36}$/);

  const putCommand = commands.find((command) => command instanceof PutCommand);
  assert.ok(putCommand);
  assert.equal(putCommand.input.TableName, "jobs-table");
  assert.equal(putCommand.input.Item.status, "QUEUED");
  assert.equal(putCommand.input.Item.payload.orderId, "1234");

  const sendCommand = commands.find(
    (command) => command instanceof SendMessageCommand,
  );
  assert.ok(sendCommand);
  assert.equal(sendCommand.input.QueueUrl, process.env.WORK_QUEUE_URL);
  assert.equal(JSON.parse(sendCommand.input.MessageBody).jobId, body.jobId);

  assert.deepEqual(
    events.map((event) => event.name),
    [
      "demo.job.request.accepted",
      "demo.job.persisted",
      "demo.job.enqueued",
    ],
  );
  assert.equal(events[0].attributes.jobId, body.jobId);
});

test("POST /jobs rejects invalid JSON", async () => {
  const response = await submitJob.handler({
    body: "{invalid",
    isBase64Encoded: false,
  });

  assert.equal(response.statusCode, 400);
  assert.match(response.body, /valid JSON/i);
});

test("POST /jobs rejects unsupported mode", async () => {
  const response = await submitJob.handler({
    body: JSON.stringify({ mode: "explode" }),
    isBase64Encoded: false,
  });

  assert.equal(response.statusCode, 400);
  assert.match(response.body, /mode must be one of/i);
});
