// Popup script for AITBC Wallet extension
let currentAccount = null;
let accounts = [];

// Load wallet data on popup open
document.addEventListener('DOMContentLoaded', async function() {
    await loadWalletData();
    updateUI();
});

// Load wallet data from storage
async function loadWalletData() {
    const result = await chrome.storage.local.get(['accounts', 'currentAccount']);
    accounts = result.accounts || [];
    currentAccount = result.currentAccount || null;
}

// Save wallet data to storage
async function saveWalletData() {
    await chrome.storage.local.set({
        accounts: accounts,
        currentAccount: currentAccount
    });
}

// Update UI with current wallet state
function updateUI() {
    const addressEl = document.getElementById('accountAddress');
    const balanceEl = document.getElementById('balance');
    
    if (currentAccount) {
        addressEl.textContent = currentAccount.address;
        balanceEl.textContent = `${currentAccount.balance || 0} AITBC`;
    } else {
        addressEl.textContent = 'Not connected';
        balanceEl.textContent = '0 AITBC';
    }
}

// Create a new account
async function createAccount() {
    // Generate a new private key and address
    const privateKey = generatePrivateKey();
    const address = await generateAddress(privateKey);
    
    const newAccount = {
        address: address,
        privateKey: privateKey,
        balance: 0,
        created: new Date().toISOString()
    };
    
    accounts.push(newAccount);
    currentAccount = newAccount;
    await saveWalletData();
    updateUI();
    
    alert('New account created! Please save your private key securely.');
}

// Import account from private key
async function importAccount() {
    const privateKey = prompt('Enter your private key:');
    if (!privateKey) return;
    
    try {
        const address = await generateAddress(privateKey);
        
        // Check if account already exists
        const existing = accounts.find(a => a.address === address);
        if (existing) {
            currentAccount = existing;
        } else {
            currentAccount = {
                address: address,
                privateKey: privateKey,
                balance: 0,
                created: new Date().toISOString()
            };
            accounts.push(currentAccount);
        }
        
        await saveWalletData();
        updateUI();
        alert('Account imported successfully!');
    } catch (error) {
        alert('Invalid private key!');
    }
}

// Send tokens
async function sendTokens() {
    if (!currentAccount) {
        alert('Please create or import an account first!');
        return;
    }
    
    const to = prompt('Send to address:');
    const amount = prompt('Amount:');
    
    if (!to || !amount) return;
    
    // In a real implementation, this would create and sign a transaction
    alert(`Would send ${amount} AITBC to ${to}`);
}

// Receive tokens
function receiveTokens() {
    if (!currentAccount) {
        alert('Please create or import an account first!');
        return;
    }
    
    alert(`Your receiving address:\n${currentAccount.address}`);
}

// View on explorer
function viewOnExplorer() {
    if (!currentAccount) {
        alert('Please create or import an account first!');
        return;
    }
    
    chrome.tabs.create({ url: `https://aitbc.bubuit.net/explorer/address/${currentAccount.address}` });
}

// Generate a random private key (demo only)
function generatePrivateKey() {
    const array = new Uint8Array(32);
    crypto.getRandomValues(array);
    return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('');
}

// Generate address from private key (demo only)
async function generateAddress(privateKey) {
    // In a real implementation, this would derive the address from the private key
    // using the appropriate cryptographic algorithm
    const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(privateKey));
    return 'aitbc1' + Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('').substring(0, 40);
}

// Listen for connection requests from dApps
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.method === 'connect') {
        // Show connection dialog
        const connected = confirm(`Allow this site to connect to your AITBC Wallet?`);
        
        if (connected && currentAccount) {
            sendResponse({
                success: true,
                address: currentAccount.address
            });
        } else {
            sendResponse({
                success: false,
                error: 'User rejected connection'
            });
        }
    }
    
    return true; // Keep the message channel open for async response
});
