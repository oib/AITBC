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

export interface AddressDetailResponse extends AddressSummary {}
export interface AddressListResponse {
  items: AddressSummary[];
  next_offset?: number | string | null;
}

export interface ReceiptSummary {
  receiptId: string;
  miner: string;
  coordinator: string;
  issuedAt: string;
  status: string;
  payload?: {
    minerSignature?: string;
    coordinatorSignature?: string;
  };
}

export interface ReceiptListResponse {
  jobId: string;
  items: ReceiptSummary[];
}
