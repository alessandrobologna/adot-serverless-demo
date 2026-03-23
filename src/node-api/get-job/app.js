"use strict";

const { trace } = require("@opentelemetry/api");
const { DynamoDBClient } = require("@aws-sdk/client-dynamodb");
const {
  DynamoDBDocumentClient,
  GetCommand,
} = require("@aws-sdk/lib-dynamodb");

const ddbClient = DynamoDBDocumentClient.from(new DynamoDBClient({}), {
  marshallOptions: { removeUndefinedValues: true },
});

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

exports.handler = async (event) => {
  const jobId = event.pathParameters?.jobId;
  if (!jobId) {
    addSpanEvent("demo.job.lookup.invalid_request");
    return response(400, {
      message: "jobId is required.",
    });
  }

  const result = await ddbClient.send(
    new GetCommand({
      TableName: process.env.JOBS_TABLE_NAME,
      Key: { jobId },
    }),
  );

  if (!result.Item) {
    addSpanEvent("demo.job.lookup.miss", {
      jobId,
    });
    return response(404, {
      message: `Job ${jobId} was not found.`,
    });
  }

  addSpanEvent("demo.job.lookup.hit", {
    jobId,
    status: String(result.Item.status ?? "UNKNOWN"),
  });

  return response(200, result.Item);
};
