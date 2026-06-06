// Main exports
export { AitbcClient } from "./client";

// Type exports
export type {
  ClientOptions,
  RequestOptions,
  MatchRequest,
  MatchResponse,
  HealthResponse,
  MetricsResponse,
  WalletSignRequest,
  WalletSignResponse,
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

import { AitbcClient } from "./client";
import type { ClientOptions } from "./types";

// Utility functions
export function createClient(options: ClientOptions): AitbcClient {
  return new AitbcClient(options);
}

// Default configuration
export const DEFAULT_CONFIG = {
  baseUrl: "https://aitbc.bubuit.net",
  timeout: 30000,
} as const;

// Version
export const VERSION = "0.1.0";
