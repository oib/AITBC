import { CONFIG, type DataMode } from "../config";
import { notifyError } from "../components/notifications";
import type {
  BlockListResponse,
  TransactionListResponse,
  AddressDetailResponse,
  AddressListResponse,
  ReceiptListResponse,
  BlockSummary,
  TransactionSummary,
  AddressSummary,
  ReceiptSummary,
} from "./models.ts";

const STORAGE_KEY = "aitbc-explorer:data-mode";

function loadStoredMode(): DataMode | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    if (value === "mock" || value === "live") {
      return value as DataMode;
    }
  } catch (error) {
    console.warn("[Explorer] Unable to read stored data mode", error);
  }
  return null;
}

const initialMode = loadStoredMode() ?? CONFIG.dataMode;
let currentMode: DataMode = initialMode;

function syncDocumentMode(mode: DataMode): void {
  if (typeof document !== "undefined") {
    document.documentElement.dataset.mode = mode;
  }
}

syncDocumentMode(currentMode);

export function getDataMode(): DataMode {
  return currentMode;
}

export function setDataMode(mode: DataMode): void {
  currentMode = mode;
  syncDocumentMode(mode);
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(STORAGE_KEY, mode);
    } catch (error) {
      console.warn("[Explorer] Failed to persist data mode", error);
    }
  }
}

export async function fetchBlocks(): Promise<BlockSummary[]> {
  if (getDataMode() === "mock") {
    const data = await fetchMock<BlockListResponse>("blocks");
    return data.items;
  }

  try {
    const response = await fetch(`${CONFIG.apiBaseUrl}/v1/explorer/blocks`);
    if (!response.ok) {
      throw new Error(`Failed to fetch blocks: ${response.status} ${response.statusText}`);
    }
    const data = (await response.json()) as BlockListResponse;
    return data.items;
  } catch (error) {
    console.error("[Explorer] Failed to fetch live block data", error);
    notifyError("Unable to load live block data from coordinator. Showing placeholders.");
    return [];
  }
}

export async function fetchTransactions(): Promise<TransactionSummary[]> {
  if (getDataMode() === "mock") {
    const data = await fetchMock<TransactionListResponse>("transactions");
    return data.items;
  }

  try {
    const response = await fetch(`${CONFIG.apiBaseUrl}/v1/explorer/transactions`);
    if (!response.ok) {
      throw new Error(`Failed to fetch transactions: ${response.status} ${response.statusText}`);
    }
    const data = (await response.json()) as TransactionListResponse;
    return data.items;
  } catch (error) {
    console.error("[Explorer] Failed to fetch live transaction data", error);
    notifyError("Unable to load transactions from coordinator. Showing placeholders.");
    return [];
  }
}

export async function fetchAddresses(): Promise<AddressSummary[]> {
  if (getDataMode() === "mock") {
    const data = await fetchMock<AddressDetailResponse | AddressDetailResponse[]>("addresses");
    return Array.isArray(data) ? data : [data];
  }

  try {
    const response = await fetch(`${CONFIG.apiBaseUrl}/v1/explorer/addresses`);
    if (!response.ok) {
      throw new Error(`Failed to fetch addresses: ${response.status} ${response.statusText}`);
    }
    const data = (await response.json()) as AddressListResponse;
    return data.items;
  } catch (error) {
    console.error("[Explorer] Failed to fetch live address data", error);
    notifyError("Unable to load address summaries from coordinator. Showing placeholders.");
    return [];
  }
}

export async function fetchReceipts(): Promise<ReceiptSummary[]> {
  if (getDataMode() === "mock") {
    const data = await fetchMock<ReceiptListResponse>("receipts");
    return data.items;
  }

  try {
    const response = await fetch(`${CONFIG.apiBaseUrl}/v1/explorer/receipts`);
    if (!response.ok) {
      throw new Error(`Failed to fetch receipts: ${response.status} ${response.statusText}`);
    }
    const data = (await response.json()) as ReceiptListResponse;
    return data.items;
  } catch (error) {
    console.error("[Explorer] Failed to fetch live receipt data", error);
    notifyError("Unable to load receipts from coordinator. Showing placeholders.");
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
    notifyError("Mock data is unavailable. Please verify development assets.");
    return [] as unknown as T;
  }
}
