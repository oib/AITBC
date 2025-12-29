// Content script for AITBC Wallet extension
(function() {
    // Inject the wallet API into the page
    const script = document.createElement('script');
    script.src = chrome.runtime.getURL('injected.js');
    script.onload = function() {
        this.remove();
    };
    (document.head || document.documentElement).appendChild(script);
    
    // Listen for messages from the injected script
    window.addEventListener('message', function(event) {
        // Only accept messages from our own window
        if (event.source !== window) return;
        
        if (event.data.type && event.data.type === 'AITBC_WALLET_REQUEST') {
            // Forward the request to the background script
            chrome.runtime.sendMessage(event.data, function(response) {
                // Send the response back to the page
                window.postMessage({
                    type: 'AITBC_WALLET_RESPONSE',
                    id: event.data.id,
                    response: response
                }, '*');
            });
        }
    });
})();
