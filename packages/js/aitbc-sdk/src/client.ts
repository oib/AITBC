import type {
  ClientOptions,
  MatchRequest,
  MatchResponse,
  HealthResponse,
  MetricsResponse,
  WalletSignRequest,
  WalletSignResponse,
  RequestOptions,
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

  constructor(options: ClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.apiKey = options.apiKey;
    this.basicAuth = options.basicAuth;
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

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

    return this.fetchImpl(url, {
      method,
      ...options,
      headers,
    });
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
