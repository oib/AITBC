import { describe, expect, it } from "vitest";

import { AitbcClient } from "./client";

const createClient = () =>
  new AitbcClient({
    baseUrl: "https://api.example.com",
    apiKey: "test-key",
    fetchImpl: async (input: RequestInfo | URL, init?: RequestInit) =>
      new Response(JSON.stringify({ job_id: "job", candidates: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  });

describe("AitbcClient", () => {
  it("sends match requests", async () => {
    const client = createClient();
    const response = await client.match({ jobId: "job" });
    expect(response.jobId).toBe("job");
    expect(response.candidates).toEqual([]);
  });
});
