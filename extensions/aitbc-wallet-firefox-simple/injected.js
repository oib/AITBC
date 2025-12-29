// Injected script that provides the AITBC wallet API to the dApp
(function() {
    // Create the wallet API object
    const aitbcWallet = {
        // Check if wallet is available
        isAvailable: function() {
            return true;
        },
        
        // Connect to wallet
        connect: async function() {
            return new Promise((resolve, reject) => {
                const requestId = Date.now().toString();
                
                // Send request to content script
                window.postMessage({
                    type: 'AITBC_WALLET_REQUEST',
                    id: requestId,
                    method: 'connect'
                }, '*');
                
                // Listen for response
                const messageHandler = function(event) {
                    if (event.data.type === 'AITBC_WALLET_RESPONSE' && event.data.id === requestId) {
                        window.removeEventListener('message', messageHandler);
                        console.log('Wallet response received:', event.data);
                        if (event.data.response && event.data.response.error) {
                            reject(new Error(event.data.response.error));
                        } else if (event.data.response && event.data.response.result) {
                            resolve(event.data.response.result);
                        } else if (event.data.response) {
                            resolve(event.data.response);
                        } else {
                            reject(new Error('Invalid response from wallet'));
                        }
                    }
                };
                
                window.addEventListener('message', messageHandler);
                
                // Timeout after 30 seconds
                setTimeout(() => {
                    window.removeEventListener('message', messageHandler);
                    reject(new Error('Connection timeout'));
                }, 30000);
            });
        },
        
        // Get account address
        getAccount: async function() {
            const accounts = await this.request({ method: 'accounts' });
            return accounts[0];
        },
        
        // Get balance
        getBalance: async function(address) {
            return this.request({ method: 'getBalance', params: { address } });
        },
        
        // Send transaction
        sendTransaction: async function(to, amount, data = null) {
            return this.request({ 
                method: 'sendTransaction', 
                params: { to, amount, data } 
            });
        },
        
        // Sign message
        signMessage: async function(message) {
            return this.request({ method: 'signMessage', params: { message } });
        },
        
        // Generic request method
        request: async function(payload) {
            return new Promise((resolve, reject) => {
                const requestId = Date.now().toString();
                
                window.postMessage({
                    type: 'AITBC_WALLET_REQUEST',
                    id: requestId,
                    method: payload.method,
                    params: payload.params || {}
                }, '*');
                
                const messageHandler = function(event) {
                    if (event.data.type === 'AITBC_WALLET_RESPONSE' && event.data.id === requestId) {
                        window.removeEventListener('message', messageHandler);
                        if (event.data.response && event.data.response.error) {
                            reject(new Error(event.data.response.error));
                        } else if (event.data.response) {
                            resolve(event.data.response);
                        } else {
                            reject(new Error('Invalid response from wallet'));
                        }
                    }
                };
                
                window.addEventListener('message', messageHandler);
                
                setTimeout(() => {
                    window.removeEventListener('message', messageHandler);
                    reject(new Error('Request timeout'));
                }, 30000);
            });
        }
    };
    
    // Inject the wallet API into the window object
    window.aitbcWallet = aitbcWallet;
    
    // Fire an event to notify the dApp that the wallet is ready
    window.dispatchEvent(new Event('aitbcWalletReady'));
})();
