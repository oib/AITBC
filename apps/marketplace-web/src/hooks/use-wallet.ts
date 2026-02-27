import { useState, useEffect } from 'react'

interface WalletState {
  address: string | null
  isConnected: boolean
  isConnecting: boolean
  balance: string
}

export function useWallet() {
  const [walletState, setWalletState] = useState<WalletState>({
    address: null,
    isConnected: false,
    isConnecting: false,
    balance: '0'
  })

  const connect = async () => {
    setWalletState(prev => ({ ...prev, isConnecting: true }))
    
    try {
      // Mock wallet connection - replace with actual wallet logic
      await new Promise(resolve => setTimeout(resolve, 1000))
      const mockAddress = '0x1234567890123456789012345678901234567890'
      
      setWalletState({
        address: mockAddress,
        isConnected: true,
        isConnecting: false,
        balance: '1000.0'
      })
    } catch (error) {
      setWalletState(prev => ({ ...prev, isConnecting: false }))
      throw error
    }
  }

  const disconnect = () => {
    setWalletState({
      address: null,
      isConnected: false,
      isConnecting: false,
      balance: '0'
    })
  }

  return {
    ...walletState,
    connect,
    disconnect
  }
}
