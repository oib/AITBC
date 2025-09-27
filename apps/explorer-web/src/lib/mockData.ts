import { CONFIG, type DataMode } from "../config";
import type {
  BlockListResponse,
  TransactionListResponse,
  AddressDetailResponse,
  ReceiptListResponse,
  BlockSummary,
  TransactionSummary,
  AddressSummary,
  ReceiptSummary,
} from "./models.ts";

let currentMode: DataMode = CONFIG.dataMode;

export function getDataMode(): DataMode {
  return currentMode;
}

export function setDataMode(mode: DataMode): void {
  currentMode = mode;
}

export async function fetchBlocks(): Promise<BlockSummary[]> {
  if (getDataMode() === "mock") {
    const data = await fetchMock<BlockListResponse>("blocks");
    return data.items;
  }

  try {
    const response = await fetch(`${CONFIG.apiBaseUrl}/v1/blocks`);
    if (!response.ok) {
      throw new Error(`Failed to fetch blocks: ${response.status}`);
    }
    const data = (await response.json()) as BlockListResponse;
    return data.items;
  } catch (error) {
    console.warn("[Explorer] Failed to fetch live block data", error);
    return [];
  }
}

export async function fetchTransactions(): Promise<TransactionSummary[]> {
  if (getDataMode() === "mock") {
    const data = await fetchMock<TransactionListResponse>("transactions");
    return data.items;
  }

  try {
    const response = await fetch(`${CONFIG.apiBaseUrl}/v1/transactions`);
    if (!response.ok) {
      throw new Error(`Failed to fetch transactions: ${response.status}`);
    }
    const data = (await response.json()) as TransactionListResponse;
    return data.items;
  } catch (error) {
    console.warn("[Explorer] Failed to fetch live transaction data", error);
    return [];
  }
}

export async function fetchAddresses(): Promise<AddressSummary[]> {
  if (getDataMode() === "mock") {
    const data = await fetchMock<AddressDetailResponse | AddressDetailResponse[]>("addresses");
    return Array.isArray(data) ? data : [data];
  }

  try {
    const response = await fetch(`${CONFIG.apiBaseUrl}/v1/addresses`);
    if (!response.ok) {
      throw new Error(`Failed to fetch addresses: ${response.status}`);
    }
    const data = (await response.json()) as { items: AddressDetailResponse[] } | AddressDetailResponse[];
    return Array.isArray(data) ? data : data.items;
  } catch (error) {
    console.warn("[Explorer] Failed to fetch live address data", error);
    return [];
  }
}

export async function fetchReceipts(): Promise<ReceiptSummary[]> {
  if (getDataMode() === "mock") {
    const data = await fetchMock<ReceiptListResponse>("receipts");
    return data.items;
  }

  try {
    const response = await fetch(`${CONFIG.apiBaseUrl}/v1/receipts`);
    if (!response.ok) {
      throw new Error(`Failed to fetch receipts: ${response.status}`);
    }
    const data = (await response.json()) as ReceiptListResponse;
    return data.items;
  } catch (error) {
    console.warn("[Explorer] Failed to fetch live receipt data", error);
    return [];
  }
}

async function fetchMock<T>(resource: string): Promise<T> {
  const url = `${CONFIG.mockBasePath}/${resource}.json`;
  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }

    return (await response.json()) as T;
  } catch (error) {
    console.warn(`[Explorer] Failed to fetch mock data from ${url}`, error);
    return [] as unknown as T;
  }
}
