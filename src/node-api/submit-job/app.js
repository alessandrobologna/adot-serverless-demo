"use strict";

const crypto = require("node:crypto");
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
    return response(400, {
      message: "Request body must be valid JSON.",
    });
  }

  const mode = payload.mode ?? "ok";
  if (!allowedModes.has(mode)) {
    return response(400, {
      message: "mode must be one of: ok, slow, fail",
    });
  }

  const workQueueUrl = process.env.WORK_QUEUE_URL;
  if (!workQueueUrl) {
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

  await ddbClient.send(
    new PutCommand({
      TableName: process.env.JOBS_TABLE_NAME,
      Item: item,
      ConditionExpression: "attribute_not_exists(jobId)",
    }),
  );

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

  return response(202, {
    jobId,
    mode,
    status: item.status,
  });
};
