"use strict";

const crypto = require("node:crypto");
const { trace } = require("@opentelemetry/api");
const { DynamoDBClient } = require("@aws-sdk/client-dynamodb");
const { SQSClient, SendMessageCommand } = require("@aws-sdk/client-sqs");
const {
  DynamoDBDocumentClient,
  PutCommand,
} = require("@aws-sdk/lib-dynamodb");

const ddbClient = DynamoDBDocumentClient.from(new DynamoDBClient({}), {
  marshallOptions: { removeUndefinedValues: true },
});
const sqsClient = new SQSClient({});
const allowedModes = new Set(["ok", "slow", "fail"]);

function addSpanEvent(name, attributes = {}) {
  const span = trace.getActiveSpan();
  if (span) {
    span.addEvent(name, attributes);
  }
}

function response(statusCode, body) {
  return {
    statusCode,
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify(body),
  };
}

function parseBody(event) {
  if (!event.body) {
    return {};
  }

  const rawBody = event.isBase64Encoded
    ? Buffer.from(event.body, "base64").toString("utf8")
    : event.body;

  return JSON.parse(rawBody);
}

exports.handler = async (event) => {
  let payload;

  try {
    payload = parseBody(event);
  } catch (error) {
    addSpanEvent("demo.job.request.invalid_json");
    return response(400, {
      message: "Request body must be valid JSON.",
    });
  }

  const mode = payload.mode ?? "ok";
  if (!allowedModes.has(mode)) {
    addSpanEvent("demo.job.request.invalid_mode", {
      mode: String(mode),
    });
    return response(400, {
      message: "mode must be one of: ok, slow, fail",
    });
  }

  const workQueueUrl = process.env.WORK_QUEUE_URL;
  if (!workQueueUrl) {
    addSpanEvent("demo.job.request.misconfigured_queue");
    throw new Error("WORK_QUEUE_URL is required.");
  }

  const now = new Date().toISOString();
  const jobId = crypto.randomUUID();
  const item = {
    artifactIndexedAt: null,
    artifactKey: null,
    artifactContentType: null,
    artifactSize: null,
    errorMessage: null,
    jobId,
    mode,
    payload: payload.payload,
    status: "QUEUED",
    submittedAt: now,
    updatedAt: now,
  };

  addSpanEvent("demo.job.request.accepted", {
    jobId,
    mode,
    status: item.status,
  });

  await ddbClient.send(
    new PutCommand({
      TableName: process.env.JOBS_TABLE_NAME,
      Item: item,
      ConditionExpression: "attribute_not_exists(jobId)",
    }),
  );

  addSpanEvent("demo.job.persisted", {
    jobId,
    mode,
    status: item.status,
  });

  await sqsClient.send(
    new SendMessageCommand({
      QueueUrl: workQueueUrl,
      MessageBody: JSON.stringify({
        jobId,
        mode,
        submittedAt: now,
      }),
    }),
  );

  addSpanEvent("demo.job.enqueued", {
    jobId,
    mode,
  });

  return response(202, {
    jobId,
    mode,
    status: item.status,
  });
};
