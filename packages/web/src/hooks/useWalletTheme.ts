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
  setPreference: (pref: WalletThemePreference) => Promise<void>;
}

/**
 * Read and write a wallet-bound theme preference from the AgentIdentity contract.
 *
 * ponytail: This is a stub implementation. A production build should use ethers/viem
 * to call `AgentIdentity.themePreference(address)` and the corresponding setter.
 */
export function useWalletTheme(_walletAddress?: string): UseWalletThemeResult {
  const [preference, setPref] = useState<WalletThemePreference | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(false);
  }, []);

  const setPreference = async (pref: WalletThemePreference): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      // Placeholder: integrate AgentIdentity.sol write call here.
      await new Promise((resolve) => setTimeout(resolve, 100));
      setPref(pref);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return { preference, loading, error, setPreference };
}
