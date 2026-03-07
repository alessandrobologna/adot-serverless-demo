"use strict";

const { DynamoDBClient } = require("@aws-sdk/client-dynamodb");
const {
  DynamoDBDocumentClient,
  GetCommand,
} = require("@aws-sdk/lib-dynamodb");

const ddbClient = DynamoDBDocumentClient.from(new DynamoDBClient({}), {
  marshallOptions: { removeUndefinedValues: true },
});

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
    return response(404, {
      message: `Job ${jobId} was not found.`,
    });
  }

  return response(200, result.Item);
};
