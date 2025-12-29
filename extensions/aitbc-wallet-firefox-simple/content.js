// Content script for AITBC Wallet Firefox extension
(function() {
    // Inject the wallet API into the page
    const script = document.createElement('script');
    script.src = browser.runtime.getURL('injected.js');
    script.onload = function() {
        this.remove();
    };
    (document.head || document.documentElement).appendChild(script);
    
    // Create a port to background script
    const port = browser.runtime.connect({ name: "aitbc-wallet" });
    
    // Listen for messages from the injected script
    window.addEventListener('message', function(event) {
        // Only accept messages from our own window
        if (event.source !== window) return;
        
        if (event.data.type && event.data.type === 'AITBC_WALLET_REQUEST') {
            // Add origin to the request
            const requestWithOrigin = {
                ...event.data,
                origin: window.location.origin
            };
            // Forward the request to the background script
            port.postMessage(requestWithOrigin);
        }
    });
    
    // Listen for responses from background script
    port.onMessage.addListener(function(response) {
        // Send the response back to the page
        window.postMessage({
            type: 'AITBC_WALLET_RESPONSE',
            id: response.id,
            response: {
                result: response.result,
                error: response.error
            }
        }, '*');
    });
})();
