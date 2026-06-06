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

// Blockchain Types
export interface BlockSummary {
  height: number;
  hash: string;
  timestamp: string;
  txCount: number;
  proposer: string;
}

export interface BlockListResponse {
  items: BlockSummary[];
  next_offset?: number | string | null;
}

export interface TransactionSummary {
  hash: string;
  block: number | string;
  from: string;
  to: string | null;
  value: string;
  status: string;
}

export interface TransactionListResponse {
  items: TransactionSummary[];
  next_offset?: number | string | null;
}

export interface AddressSummary {
  address: string;
  balance: string;
  txCount: number;
  lastActive: string;
  recentTransactions?: string[];
}

export interface AddressListResponse {
  items: AddressSummary[];
  next_offset?: number | string | null;
}

export interface ReceiptSummary {
  receiptId: string;
  jobId?: string;
  miner: string;
  coordinator: string;
  issuedAt: string;
  status: string;
  payload?: {
    job_id?: string;
    provider?: string;
    client?: string;
    units?: number;
    unit_type?: string;
    unit_price?: number;
    price?: number;
    minerSignature?: string;
    coordinatorSignature?: string;
    signature?: {
      alg?: string;
      key_id?: string;
      sig?: string;
    };
  };
}

export interface ReceiptListResponse {
  jobId: string;
  items: ReceiptSummary[];
}

// Marketplace Types
export interface MarketplaceOffer {
  id: string;
  provider: string;
  capacity: number;
  price: number;
  sla: string;
  status: string;
  created_at?: string;
  gpu_model?: string;
  gpu_memory_gb?: number;
  gpu_count?: number;
  cuda_version?: string;
  price_per_hour?: number;
  region?: string;
  attributes?: {
    ollama_host?: string;
    models?: string[];
    vram_mb?: number;
    driver?: string;
    [key: string]: unknown;
  };
}

export interface MarketplaceStats {
  totalOffers: number;
  openCapacity: number;
  averagePrice: number;
  activeBids: number;
}

export interface MarketplaceBid {
  provider: string;
  capacity: number;
  price: number;
  notes?: string;
}

export interface MarketplaceSession {
  token: string;
  expiresAt: number;
}

// Job Management Types
export interface JobSubmission {
  service_type: string;
  model?: string;
  parameters?: Record<string, unknown>;
  requirements?: Record<string, unknown>;
}

export interface Job {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  createdAt: string;
  updatedAt: string;
  serviceType: string;
  model?: string;
  parameters?: Record<string, unknown>;
  result?: unknown;
  error?: string;
}

export interface JobStatus {
  id: string;
  status: Job["status"];
  progress?: number;
  estimatedCompletion?: string;
}

export interface JobResult {
  id: string;
  output: unknown;
  metadata?: Record<string, unknown>;
  receipts?: ReceiptSummary[];
}

// Client Configuration
export interface ClientOptions {
  baseUrl: string;
  apiKey?: string;
  basicAuth?: {
    username: string;
    password: string;
  };
  fetchImpl?: typeof fetch;
  timeout?: number;
}

export interface RequestOptions extends RequestInit {
  query?: Record<string, string | number | boolean | undefined>;
}
