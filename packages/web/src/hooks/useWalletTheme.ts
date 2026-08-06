import { useEffect, useState } from "react";

export type WalletThemePreference =
  | "system"
  | "light"
  | "dark"
  | "high-contrast";

export interface UseWalletThemeResult {
  preference: WalletThemePreference | null;
  loading: boolean;
  error: string | null;
  /** True while no contract integration is wired up. Check this before trusting a write. */
  notImplemented: boolean;
  setPreference: (pref: WalletThemePreference) => Promise<void>;
}

const NOT_IMPLEMENTED_MESSAGE =
  "Wallet-bound theme preferences are not implemented: no AgentIdentity contract call is " +
  "wired up. Use the local theme preference (useAitbcTheme) instead.";

/**
 * Read and write a wallet-bound theme preference from the AgentIdentity contract.
 *
 * **Not implemented.** There is no contract integration behind this hook. It previously
 * presented as though there were: `setPreference` awaited a 100ms `setTimeout` and updated
 * local state, so a caller saw a resolved promise and a changed value and had every reason
 * to believe the preference had been persisted to the wallet. Nothing was written anywhere,
 * and the value vanished on reload.
 *
 * It now reports the gap instead of hiding it: `notImplemented` is true, `error` carries an
 * explanation, and `setPreference` rejects rather than resolving. A production build should
 * use ethers/viem to call `AgentIdentity.themePreference(address)` and its setter, at which
 * point this contract can be honoured for real.
 */
export function useWalletTheme(_walletAddress?: string): UseWalletThemeResult {
  const [preference] = useState<WalletThemePreference | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(false);
    setError(NOT_IMPLEMENTED_MESSAGE);
  }, []);

  const setPreference = async (_pref: WalletThemePreference): Promise<void> => {
    // Reject rather than resolve. A resolved promise here is a claim that the preference
    // was persisted on chain.
    throw new Error(NOT_IMPLEMENTED_MESSAGE);
  };

  return { preference, loading, error, notImplemented: true, setPreference };
}
