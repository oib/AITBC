import type {
  ClientOptions,
  MatchRequest,
  MatchResponse,
  HealthResponse,
  MetricsResponse,
  WalletSignRequest,
  WalletSignResponse,
  RequestOptions,
  BlockSummary,
  BlockListResponse,
  TransactionSummary,
  TransactionListResponse,
  AddressSummary,
  AddressListResponse,
  ReceiptSummary,
  ReceiptListResponse,
  MarketplaceOffer,
  MarketplaceStats,
  MarketplaceBid,
  MarketplaceSession,
  JobSubmission,
  Job,
  JobStatus,
  JobResult,
} from "./types";

const DEFAULT_HEADERS = {
  "Content-Type": "application/json",
  Accept: "application/json",
};

export class AitbcClient {
  private readonly baseUrl: string;
  private readonly apiKey?: string;
  private readonly basicAuth?: ClientOptions["basicAuth"];
  private readonly fetchImpl: typeof fetch;
  private readonly timeout?: number;

  constructor(options: ClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.apiKey = options.apiKey;
    this.basicAuth = options.basicAuth;
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.timeout = options.timeout;
  }

  // Coordinator API Methods
  async match(payload: MatchRequest, options?: RequestOptions): Promise<MatchResponse> {
    const raw = await this.request<any>("POST", "/v1/match", {
      ...options,
      body: JSON.stringify({
        job_id: payload.jobId,
        requirements: payload.requirements ?? {},
        hints: payload.hints ?? {},
        top_k: payload.topK ?? 1,
      }),
    });
    return {
      jobId: raw.job_id,
      candidates: (raw.candidates ?? []).map((candidate: any) => ({
        minerId: candidate.miner_id,
        addr: candidate.addr,
        proto: candidate.proto,
        score: candidate.score,
        explain: candidate.explain,
        etaMs: candidate.eta_ms,
        price: candidate.price,
      })),
    };
  }

  async health(options?: RequestOptions): Promise<HealthResponse> {
    const raw = await this.request<any>("GET", "/v1/health", options);
    return {
      status: raw.status,
      db: raw.db,
      redis: raw.redis,
      minersOnline: raw.miners_online,
      dbError: raw.db_error ?? null,
      redisError: raw.redis_error ?? null,
    };
  }

  async metrics(options?: RequestOptions): Promise<MetricsResponse> {
    const response = await this.rawRequest("GET", "/metrics", options);
    const raw = await response.text();
    return { raw };
  }

  async sign(request: WalletSignRequest, options?: RequestOptions): Promise<WalletSignResponse> {
    return this.request<WalletSignResponse>("POST", `/v1/wallets/${encodeURIComponent(request.walletId)}/sign`, {
      ...options,
      body: JSON.stringify({
        password: request.password,
        message_base64: request.messageBase64,
      }),
    });
  }

  // Job Management Methods
  async submitJob(job: JobSubmission, options?: RequestOptions): Promise<Job> {
    return this.request<Job>("POST", "/v1/jobs", {
      ...options,
      body: JSON.stringify(job),
    });
  }

  async getJob(jobId: string, options?: RequestOptions): Promise<Job> {
    return this.request<Job>("GET", `/v1/jobs/${jobId}`, options);
  }

  async getJobStatus(jobId: string, options?: RequestOptions): Promise<JobStatus> {
    return this.request<JobStatus>("GET", `/v1/jobs/${jobId}/status`, options);
  }

  async getJobResult(jobId: string, options?: RequestOptions): Promise<JobResult> {
    return this.request<JobResult>("GET", `/v1/jobs/${jobId}/result`, options);
  }

  async cancelJob(jobId: string, options?: RequestOptions): Promise<void> {
    await this.request<void>("DELETE", `/v1/jobs/${jobId}`, options);
  }

  async listJobs(options?: RequestOptions): Promise<{ items: Job[]; next_offset?: string }> {
    return this.request<{ items: Job[]; next_offset?: string }>("GET", "/v1/jobs", options);
  }

  // Receipt Methods
  async getJobReceipts(jobId: string, options?: RequestOptions): Promise<ReceiptListResponse> {
    return this.request<ReceiptListResponse>("GET", `/v1/jobs/${jobId}/receipts`, options);
  }

  async verifyReceipt(receipt: ReceiptSummary, options?: RequestOptions): Promise<{ valid: boolean }> {
    return this.request<{ valid: boolean }>("POST", "/v1/receipts/verify", {
      ...options,
      body: JSON.stringify(receipt),
    });
  }

  // Blockchain Explorer Methods
  async getBlocks(options?: RequestOptions): Promise<BlockListResponse> {
    return this.request<BlockListResponse>("GET", "/v1/explorer/blocks", options);
  }

  async getBlock(height: string | number, options?: RequestOptions): Promise<BlockSummary> {
    return this.request<BlockSummary>("GET", `/v1/explorer/blocks/${height}`, options);
  }

  async getTransactions(options?: RequestOptions): Promise<TransactionListResponse> {
    return this.request<TransactionListResponse>("GET", "/v1/explorer/transactions", options);
  }

  async getTransaction(hash: string, options?: RequestOptions): Promise<TransactionSummary> {
    return this.request<TransactionSummary>("GET", `/v1/explorer/transactions/${hash}`, options);
  }

  async getAddresses(options?: RequestOptions): Promise<AddressListResponse> {
    return this.request<AddressListResponse>("GET", "/v1/explorer/addresses", options);
  }

  async getAddress(address: string, options?: RequestOptions): Promise<AddressSummary> {
    return this.request<AddressSummary>("GET", `/v1/explorer/addresses/${address}`, options);
  }

  async getReceipts(options?: RequestOptions): Promise<ReceiptListResponse> {
    return this.request<ReceiptListResponse>("GET", "/v1/explorer/receipts", options);
  }

  // Marketplace Methods
  async getMarketplaceStats(options?: RequestOptions): Promise<MarketplaceStats> {
    return this.request<MarketplaceStats>("GET", "/v1/marketplace/stats", options);
  }

  async getMarketplaceOffers(options?: RequestOptions): Promise<MarketplaceOffer[]> {
    return this.request<MarketplaceOffer[]>("GET", "/v1/marketplace/offers", options);
  }

  async getMarketplaceOffer(offerId: string, options?: RequestOptions): Promise<MarketplaceOffer> {
    return this.request<MarketplaceOffer>("GET", `/v1/marketplace/offers/${offerId}`, options);
  }

  async submitMarketplaceBid(bid: MarketplaceBid, options?: RequestOptions): Promise<void> {
    await this.request<void>("POST", "/v1/marketplace/bids", {
      ...options,
      body: JSON.stringify(bid),
    });
  }

  // Authentication Methods
  async login(credentials: { username: string; password: string }, options?: RequestOptions): Promise<MarketplaceSession> {
    return this.request<MarketplaceSession>("POST", "/v1/users/login", {
      ...options,
      body: JSON.stringify(credentials),
    });
  }

  async logout(options?: RequestOptions): Promise<void> {
    await this.request<void>("POST", "/v1/users/logout", options);
  }

  private async request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
    const response = await this.rawRequest(method, path, options);
    const text = await response.text();
    if (!response.ok) {
      throw new Error(`AITBC request failed (${response.status}): ${text || response.statusText}`);
    }
    return text ? (JSON.parse(text) as T) : ({} as T);
  }

  private async rawRequest(method: string, path: string, options: RequestOptions = {}): Promise<Response> {
    const url = this.buildUrl(path, options.query);
    const headers = this.buildHeaders(options.headers);

    const controller = new AbortController();
    const timeoutId = this.timeout ? setTimeout(() => controller.abort(), this.timeout) : undefined;

    try {
      return await this.fetchImpl(url, {
        method,
        signal: controller.signal,
        ...options,
        headers,
      });
    } finally {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    }
  }

  private buildUrl(path: string, query?: RequestOptions["query"]): string {
    const url = new URL(`${this.baseUrl}${path}`);
    if (query) {
      for (const [key, value] of Object.entries(query)) {
        if (value !== undefined) {
          url.searchParams.set(key, String(value));
        }
      }
    }
    return url.toString();
  }

  private buildHeaders(extra?: HeadersInit): HeadersInit {
    const headers: Record<string, string> = { ...DEFAULT_HEADERS };
    if (this.apiKey) {
      headers["X-Api-Key"] = this.apiKey;
    }
    if (this.basicAuth) {
      const token = btoa(`${this.basicAuth.username}:${this.basicAuth.password}`);
      headers["Authorization"] = `Basic ${token}`;
    }
    if (extra) {
      if (extra instanceof Headers) {
        extra.forEach((value, key) => {
          headers[key] = value;
        });
      } else if (Array.isArray(extra)) {
        for (const [key, value] of extra) {
          headers[key] = value;
        }
      } else {
        Object.assign(headers, extra as Record<string, string>);
      }
    }
    return headers;
  }
}
