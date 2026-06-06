#!/bin/bash
# Script to return testnet Bitcoin

RETURN_ADDRESS="tb1qerzrlxcfu24davlur5sqmgzzgsal6wusda40er"

echo "Checking balance..."
BALANCE=$(bitcoin-cli -testnet -rpcwallet=aitbc_exchange getbalance)

if [ "$(echo "$BALANCE > 0" | bc)" -eq 1 ]; then
    echo "Current balance: $BALANCE BTC"
    echo "Sending to return address: $RETURN_ADDRESS"
    
    # Calculate amount to send (balance minus small fee)
    SEND_AMOUNT=$(echo "$BALANCE - 0.00001" | bc)
    
    TXID=$(bitcoin-cli -testnet -rpcwallet=aitbc_exchange sendtoaddress "$RETURN_ADDRESS" "$SEND_AMOUNT")
    echo "Transaction sent! TXID: $TXID"
    echo "Explorer: https://blockstream.info/testnet/tx/$TXID"
else
    echo "No Bitcoin to return. Current balance: $BALANCE BTC"
fi
