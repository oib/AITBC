import { verify as verifySignature, createPublicKey } from "crypto";
import type { ReceiptListResponse, ReceiptSummary, RequestOptions } from "./types";
import { AitbcClient } from "./client";

export interface PaginatedReceipts {
  items: ReceiptSummary[];
  nextCursor?: string | null;
}

export interface ReceiptValidationResult {
  valid: boolean;
  reason?: string;
}

export interface ReceiptValidationOptions extends RequestOptions {
  minerVerifier?: (receipt: ReceiptSummary) => Promise<boolean> | boolean;
  coordinatorVerifier?: (receipt: ReceiptSummary) => Promise<boolean> | boolean;
  minerPublicKeyPem?: string;
  coordinatorPublicKeyPem?: string;
  signatureAlgorithm?: "ed25519" | "secp256k1" | "rsa" | string;
}

export interface ReceiptServiceOptions {
  client: AitbcClient;
  maxRetries?: number;
  retryDelayMs?: number;
  minerPublicKeyPem?: string;
  coordinatorPublicKeyPem?: string;
  signatureAlgorithm?: "ed25519" | "secp256k1" | "rsa" | string;
}

export class ReceiptService {
  private client: AitbcClient;
  private maxRetries: number;
  private retryDelayMs: number;
  private minerPublicKeyPem?: string;
  private coordinatorPublicKeyPem?: string;
  private signatureAlgorithm?: string;

  constructor(opts: ReceiptServiceOptions) {
    this.client = opts.client;
    this.maxRetries = opts.maxRetries ?? 3;
    this.retryDelayMs = opts.retryDelayMs ?? 250;
    this.minerPublicKeyPem = opts.minerPublicKeyPem;
    this.coordinatorPublicKeyPem = opts.coordinatorPublicKeyPem;
    this.signatureAlgorithm = opts.signatureAlgorithm ?? "ed25519";
  }

  async getJobReceipts(
    jobId: string,
    cursor?: string,
    limit: number = 50,
    options?: RequestOptions,
  ): Promise<PaginatedReceipts> {
    let attempt = 0;
    let lastError: unknown;

    while (attempt <= this.maxRetries) {
      try {
        const data = await this.client.request<ReceiptListResponse & { next_cursor?: string }>(
          "GET",
          `/v1/jobs/${jobId}/receipts`,
          {
            ...options,
            query: {
              cursor,
              limit,
            },
          }
        );
        return {
          items: (data.items ?? []).filter((r) => !r.jobId || r.jobId === jobId),
          nextCursor: data.next_cursor ?? (data as any).nextCursor ?? null,
        };
      } catch (err) {
        lastError = err;
        attempt += 1;
        if (attempt > this.maxRetries) break;
        await this.delay(this.retryDelayMs * attempt);
      }
    }

    throw lastError ?? new Error("Failed to fetch receipts");
  }

  async validateReceipt(receipt: ReceiptSummary, options?: ReceiptValidationOptions): Promise<ReceiptValidationResult> {
    // Placeholder for full cryptographic verification: delegate to coordinator API
    const {
      minerVerifier,
      coordinatorVerifier,
      minerPublicKeyPem,
      coordinatorPublicKeyPem,
      signatureAlgorithm,
      ...requestOptions
    } = options ?? {};
    try {
      const data = await this.client.request<{ valid: boolean; reason?: string }>(
        "POST",
        "/v1/receipts/verify",
        {
          ...requestOptions,
          body: JSON.stringify(this.buildVerificationPayload(receipt)),
        }
      );
      return { valid: !!data.valid, reason: data.reason };
    } catch (err) {
      // Fallback to local checks if API unavailable
      const local = await this.validateLocally(
        receipt,
        minerVerifier,
        coordinatorVerifier,
        minerPublicKeyPem ?? this.minerPublicKeyPem,
        coordinatorPublicKeyPem ?? this.coordinatorPublicKeyPem,
        signatureAlgorithm ?? this.signatureAlgorithm ?? "ed25519"
      );
      return local.valid ? local : { valid: false, reason: (err as Error).message };
    }
  }

  buildVerificationPayload(receipt: ReceiptSummary) {
    return {
      receipt_id: receipt.receiptId,
      job_id: receipt.jobId,
      miner: receipt.miner,
      coordinator: receipt.coordinator,
      issued_at: receipt.issuedAt,
      status: receipt.status,
      payload: receipt.payload,
    };
  }

  async validateLocally(
    receipt: ReceiptSummary,
    minerVerifier?: (receipt: ReceiptSummary) => Promise<boolean> | boolean,
    coordinatorVerifier?: (receipt: ReceiptSummary) => Promise<boolean> | boolean,
    minerPublicKeyPem?: string,
    coordinatorPublicKeyPem?: string,
    signatureAlgorithm: string = "ed25519",
  ): Promise<ReceiptValidationResult> {
    const payload = receipt.payload ?? {};
    const sig = payload.signature ?? {};
    const minerSig = payload.minerSignature ?? sig.sig;
    const coordinatorSig = payload.coordinatorSignature ?? sig.sig;

    if (!minerSig) {
      return { valid: false, reason: "missing miner signature" };
    }
    if (!coordinatorSig) {
      return { valid: false, reason: "missing coordinator signature" };
    }
    if (!payload.job_id && receipt.jobId) {
      return { valid: false, reason: "missing job_id in payload" };
    }

    const payloadForSig = this.sanitizePayload(payload);

    if (minerVerifier) {
      const ok = await minerVerifier(receipt);
      if (!ok) return { valid: false, reason: "miner signature invalid" };
    } else if (minerPublicKeyPem) {
      const ok = this.verifyWithCrypto(minerSig, minerPublicKeyPem, payloadForSig, signatureAlgorithm);
      if (!ok) return { valid: false, reason: "miner signature invalid" };
    }
    if (coordinatorVerifier) {
      const ok = await coordinatorVerifier(receipt);
      if (!ok) return { valid: false, reason: "coordinator signature invalid" };
    } else if (coordinatorPublicKeyPem) {
      const ok = this.verifyWithCrypto(coordinatorSig, coordinatorPublicKeyPem, payloadForSig, signatureAlgorithm);
      if (!ok) return { valid: false, reason: "coordinator signature invalid" };
    }
    return { valid: true };
  }

  private sanitizePayload(payload: Record<string, unknown>): Record<string, unknown> {
    const { _signature, _minerSignature, _coordinatorSignature, ...rest } = payload ?? {};
    return rest;
  }

  private verifyWithCrypto(
    signatureBase64: string,
    publicKeyPem: string,
    payload: Record<string, unknown>,
    alg: string,
  ): boolean {
    try {
      const key = createPublicKey(publicKeyPem);
      const message = Buffer.from(JSON.stringify(payload ?? {}));
      const sig = Buffer.from(signatureBase64, "base64");

      if (alg.toLowerCase() === "ed25519") {
        return verifySignature(null, message, key, sig);
      }
      if (alg.toLowerCase() === "secp256k1") {
        return verifySignature("sha256", message, { key, dsaEncoding: "ieee-p1363" }, sig);
      }
      if (alg.toLowerCase().startsWith("rsa")) {
        return verifySignature("sha256", message, key, sig);
      }
      // Unknown alg: fail closed
      return false;
    } catch (e) {
      return false;
    }
  }

  private async delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
