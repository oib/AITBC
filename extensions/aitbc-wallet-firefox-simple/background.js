// Background script for Firefox extension
// Handles messages from content scripts and manages wallet state

let currentPort = null;

// Listen for connection from content script
browser.runtime.onConnect.addListener(function(port) {
    if (port.name === "aitbc-wallet") {
        currentPort = port;
        
        port.onMessage.addListener(function(request) {
            handleWalletRequest(request, port);
        });
        
        port.onDisconnect.addListener(function() {
            currentPort = null;
        });
    }
});

// Handle wallet requests from dApps
async function handleWalletRequest(request, port) {
    const { method, params, id } = request;
    
    try {
        switch (method) {
            case 'connect':
                const response = await handleConnect(request);
                port.postMessage({ id, result: response });
                break;
                
            case 'accounts':
                const accounts = await getAccounts();
                port.postMessage({ id, result: accounts });
                break;
                
            case 'getBalance':
                const balance = await getBalance(params.address);
                port.postMessage({ id, result: balance });
                break;
                
            case 'sendTransaction':
                const txResult = await sendTransaction(params);
                port.postMessage({ id, result: txResult });
                break;
                
            case 'signMessage':
                const signature = await signMessage(params.message);
                port.postMessage({ id, result: signature });
                break;
                
            default:
                port.postMessage({ id, error: 'Unknown method: ' + method });
        }
    } catch (error) {
        port.postMessage({ id, error: error.message });
    }
}

// Handle connection request from dApp
async function handleConnect(request) {
    // Get current account
    const result = await browser.storage.local.get(['currentAccount']);
    
    if (!result.currentAccount) {
        throw new Error('No account found. Please create or import an account first.');
    }
    
    // For now, auto-approve connections from aitbc.bubuit.net
    if (request.origin && (request.origin === 'https://aitbc.bubuit.net' || request.origin.includes('aitbc.bubuit.net'))) {
        return {
            success: true,
            address: result.currentAccount.address
        };
    }
    
    // For debugging, let's allow localhost too
    if (request.origin && request.origin.includes('localhost')) {
        return {
            success: true,
            address: result.currentAccount.address
        };
    }
    
    // For other sites, would show a connection dialog
    throw new Error(`Connection not allowed for origin: ${request.origin}`);
}

// Get all accounts
async function getAccounts() {
    const result = await browser.storage.local.get(['accounts']);
    const accounts = result.accounts || [];
    return accounts.map(acc => acc.address);
}

// Get balance for an address
async function getBalance(address) {
    // In a real implementation, this would query the blockchain
    // For demo, return stored balance
    const result = await browser.storage.local.get(['accounts']);
    const accounts = result.accounts || [];
    const account = accounts.find(acc => acc.address === address);
    
    return {
        address: address,
        balance: account ? account.balance || 0 : 0,
        symbol: 'AITBC'
    };
}

// Send transaction
async function sendTransaction(params) {
    // In a real implementation, this would create, sign, and broadcast a transaction
    const { to, amount, data } = params;
    
    // Get current account
    const result = await browser.storage.local.get(['currentAccount']);
    const account = result.currentAccount;
    
    if (!account) {
        throw new Error('No account connected');
    }
    
    // Confirm transaction
    const confirmed = confirm(`Send ${amount} AITBC to ${to}?\n\nFrom: ${account.address}`);
    if (!confirmed) {
        throw new Error('Transaction rejected');
    }
    
    // Return mock transaction hash
    return {
        hash: '0x' + Array.from(crypto.getRandomValues(new Uint8Array(32)), b => b.toString(16).padStart(2, '0')).join(''),
        status: 'pending'
    };
}

// Sign message
async function signMessage(message) {
    // Get current account
    const result = await browser.storage.local.get(['currentAccount']);
    const account = result.currentAccount;
    
    if (!account) {
        throw new Error('No account connected');
    }
    
    // Confirm signing
    const confirmed = confirm(`Sign the following message?\n\n"${message}"\n\nAccount: ${account.address}`);
    if (!confirmed) {
        throw new Error('Message signing rejected');
    }
    
    // In a real implementation, this would sign with the private key
    // For demo, return a mock signature
    const encoder = new TextEncoder();
    const data = encoder.encode(message + account.privateKey);
    const hash = await crypto.subtle.digest('SHA-256', data);
    
    return Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('');
}
