"use strict";

const assert = require("node:assert/strict");
const { afterEach, test, mock } = require("node:test");
const { DynamoDBDocumentClient, GetCommand } = require("@aws-sdk/lib-dynamodb");

const getJob = require("../../src/node-api/get-job/app");

afterEach(() => {
  mock.restoreAll();
  delete process.env.JOBS_TABLE_NAME;
});

test("GET /jobs/{jobId} returns the stored item", async () => {
  process.env.JOBS_TABLE_NAME = "jobs-table";

  mock.method(DynamoDBDocumentClient.prototype, "send", async (command) => {
    assert.ok(command instanceof GetCommand);
    assert.equal(command.input.TableName, "jobs-table");
    assert.equal(command.input.Key.jobId, "job-123");
    return {
      Item: {
        jobId: "job-123",
        status: "COMPLETED",
      },
    };
  });

  const response = await getJob.handler({
    pathParameters: { jobId: "job-123" },
  });

  assert.equal(response.statusCode, 200);
  assert.deepEqual(JSON.parse(response.body), {
    jobId: "job-123",
    status: "COMPLETED",
  });
});

test("GET /jobs/{jobId} returns 404 when the item is missing", async () => {
  mock.method(DynamoDBDocumentClient.prototype, "send", async () => ({ Item: null }));

  const response = await getJob.handler({
    pathParameters: { jobId: "missing-job" },
  });

  assert.equal(response.statusCode, 404);
  assert.match(response.body, /missing-job/);
});
