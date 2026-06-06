import { describe, expect, it } from "vitest";
import { generateKeyPairSync, sign } from "crypto";
import { ReceiptService } from "./receipts";
import type { ReceiptSummary } from "./types";

class ThrowingClient {
  async request() {
    throw new Error("offline");
  }
}

describe("ReceiptService signature verification", () => {
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const publicKeyPem = publicKey
    .export({ type: "spki", format: "pem" })
    .toString();

  const baseReceipt: ReceiptSummary = {
    receiptId: "r1",
    jobId: "job-123",
    miner: "miner-1",
    coordinator: "coord-1",
    issuedAt: new Date().toISOString(),
    status: "completed",
    payload: {
      job_id: "job-123",
      provider: "miner-1",
      client: "client-1",
    },
  };

  const signPayload = (payload: Record<string, unknown>): string => {
    const message = Buffer.from(JSON.stringify(payload));
    return sign(null, message, privateKey).toString("base64");
  };

  it("validates with provided PEM keys", async () => {
    const sig = signPayload(baseReceipt.payload!);
    const receipt: ReceiptSummary = {
      ...baseReceipt,
      payload: {
        ...baseReceipt.payload,
        minerSignature: sig,
        coordinatorSignature: sig,
      },
    };

    const svc = new ReceiptService({
      client: new ThrowingClient() as any,
      minerPublicKeyPem: publicKeyPem,
      coordinatorPublicKeyPem: publicKeyPem,
      signatureAlgorithm: "ed25519",
    });

    const result = await svc.validateReceipt(receipt);
    expect(result.valid).toBe(true);
  });

  it("fails with bad signature", async () => {
    const receipt: ReceiptSummary = {
      ...baseReceipt,
      payload: {
        ...baseReceipt.payload,
        minerSignature: "bad",
        coordinatorSignature: "bad",
      },
    };

    const svc = new ReceiptService({
      client: new ThrowingClient() as any,
      minerPublicKeyPem: publicKeyPem,
      coordinatorPublicKeyPem: publicKeyPem,
      signatureAlgorithm: "ed25519",
    });

    const result = await svc.validateReceipt(receipt);
    expect(result.valid).toBe(false);
  });
});
