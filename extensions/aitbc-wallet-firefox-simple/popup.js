// Popup script for AITBC Wallet extension
let currentAccount = null;
let accounts = [];

// Load wallet data on popup open
document.addEventListener('DOMContentLoaded', async function() {
    await loadWalletData();
    updateUI();
    
    // Check for pending connection request
    const pending = await browser.storage.local.get(['pendingConnection']);
    if (pending.pendingConnection) {
        showConnectionDialog(pending.pendingConnection);
    }
    
    // Add event listeners
    document.getElementById('createAccountBtn').addEventListener('click', createAccount);
    document.getElementById('importAccountBtn').addEventListener('click', importAccount);
    document.getElementById('sendTokensBtn').addEventListener('click', sendTokens);
    document.getElementById('receiveTokensBtn').addEventListener('click', receiveTokens);
    document.getElementById('viewOnExplorerBtn').addEventListener('click', viewOnExplorer);
    document.getElementById('accountSelector').addEventListener('change', switchAccount);
});

// Load wallet data from storage
async function loadWalletData() {
    const result = await browser.storage.local.get(['accounts', 'currentAccount']);
    accounts = result.accounts || [];
    currentAccount = result.currentAccount || null;
}

// Save wallet data to storage
async function saveWalletData() {
    await browser.storage.local.set({
        accounts: accounts,
        currentAccount: currentAccount
    });
}

// Update UI with current wallet state
function updateUI() {
    const addressEl = document.getElementById('accountAddress');
    const balanceEl = document.getElementById('balance');
    const selectorEl = document.getElementById('accountSelector');
    
    // Update account selector
    selectorEl.innerHTML = '';
    if (accounts.length === 0) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'No accounts';
        selectorEl.appendChild(option);
    } else {
        accounts.forEach((account, index) => {
            const option = document.createElement('option');
            option.value = index;
            option.textContent = `Account ${index + 1} - ${account.address.substring(0, 20)}...`;
            if (currentAccount && currentAccount.address === account.address) {
                option.selected = true;
            }
            selectorEl.appendChild(option);
        });
    }
    
    // Update current account display
    if (currentAccount) {
        addressEl.textContent = currentAccount.address;
        balanceEl.textContent = `${currentAccount.balance || 0} AITBC`;
    } else {
        addressEl.textContent = 'Not connected';
        balanceEl.textContent = '0 AITBC';
    }
}

// Show connection dialog
function showConnectionDialog(pendingConnection) {
    const dialog = document.createElement('div');
    dialog.className = 'connection-dialog';
    dialog.innerHTML = `
        <div class="dialog-content">
            <h3>Connection Request</h3>
            <p>${pendingConnection.origin} wants to connect to your AITBC Wallet</p>
            <p class="address">Address: ${pendingConnection.address}</p>
            <div class="dialog-buttons">
                <button id="approveConnection" class="approve-btn">Approve</button>
                <button id="rejectConnection" class="reject-btn">Reject</button>
            </div>
        </div>
    `;
    
    // Add styles for the dialog
    const style = document.createElement('style');
    style.textContent = `
        .connection-dialog {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.8);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }
        .dialog-content {
            background: white;
            color: black;
            padding: 20px;
            border-radius: 8px;
            max-width: 300px;
            text-align: center;
        }
        .dialog-content h3 {
            margin-top: 0;
        }
        .dialog-content .address {
            font-family: monospace;
            font-size: 12px;
            word-break: break-all;
            background: #f0f0f0;
            padding: 5px;
            border-radius: 4px;
            margin: 10px 0;
        }
        .dialog-buttons {
            display: flex;
            gap: 10px;
            justify-content: center;
            margin-top: 20px;
        }
        .approve-btn {
            background: #28a745;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
        }
        .reject-btn {
            background: #dc3545;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
        }
    `;
    
    document.head.appendChild(style);
    document.body.appendChild(dialog);
    
    // Handle button clicks
    document.getElementById('approveConnection').addEventListener('click', async () => {
        await browser.storage.local.set({
            connectionResponse: {
                id: pendingConnection.id,
                approved: true
            }
        });
        await browser.storage.local.remove(['pendingConnection']);
        dialog.remove();
        style.remove();
    });
    
    document.getElementById('rejectConnection').addEventListener('click', async () => {
        await browser.storage.local.set({
            connectionResponse: {
                id: pendingConnection.id,
                approved: false
            }
        });
        await browser.storage.local.remove(['pendingConnection']);
        dialog.remove();
        style.remove();
    });
}

// Switch to a different account
async function switchAccount() {
    const selectorEl = document.getElementById('accountSelector');
    const selectedIndex = parseInt(selectorEl.value);
    
    if (isNaN(selectedIndex) || selectedIndex < 0 || selectedIndex >= accounts.length) {
        return;
    }
    
    currentAccount = accounts[selectedIndex];
    await saveWalletData();
    updateUI();
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
    
    browser.tabs.create({ url: `https://aitbc.bubuit.net/explorer/?address=${currentAccount.address}` });
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
browser.runtime.onMessage.addListener((request, sender, sendResponse) => {
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
