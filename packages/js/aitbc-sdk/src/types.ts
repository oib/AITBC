export interface MatchRequest {
  jobId: string;
  requirements?: Record<string, unknown>;
  hints?: Record<string, unknown>;
  topK?: number;
}

export interface MatchCandidate {
  minerId: string;
  addr: string;
  proto: string;
  score: number;
  explain?: string;
  etaMs?: number;
  price?: number;
}

export interface MatchResponse {
  jobId: string;
  candidates: MatchCandidate[];
}

export interface HealthResponse {
  status: "ok" | "degraded";
  db: boolean;
  redis: boolean;
  minersOnline: number;
  dbError?: string | null;
  redisError?: string | null;
}

export interface MetricsResponse {
  raw: string;
}

export interface WalletSignRequest {
  walletId: string;
  password: string;
  messageBase64: string;
}

export interface WalletSignResponse {
  walletId: string;
  signatureBase64: string;
}

export interface ClientOptions {
  baseUrl: string;
  apiKey?: string;
  basicAuth?: {
    username: string;
    password: string;
  };
  fetchImpl?: typeof fetch;
}

export interface RequestOptions extends RequestInit {
  query?: Record<string, string | number | boolean | undefined>;
}
