// Lightweight privacy-focused analytics for AITBC
// No cookies, no tracking, just basic page view metrics
(function() {
    'use strict';
    
    const script = document.currentScript;
    const host = script.getAttribute('data-host') || window.location.origin;
    const website = script.getAttribute('data-website') || 'default';
    
    // Send page view on load
    function sendPageView() {
        const data = {
            url: window.location.href,
            pathname: window.location.pathname,
            hostname: window.location.hostname,
            referrer: document.referrer,
            screenWidth: window.screen.width,
            screenHeight: window.screen.height,
            language: navigator.language,
            website: website,
            timestamp: new Date().toISOString()
        };
        
        // Use sendBeacon for reliable delivery
        if (navigator.sendBeacon) {
            navigator.sendBeacon(`${host}/api/analytics`, JSON.stringify(data));
        } else {
            // Fallback to fetch
            fetch(`${host}/api/analytics`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
                keepalive: true
            }).catch(() => {});
        }
    }
    
    // Send initial page view
    if (document.readyState === 'complete') {
        sendPageView();
    } else {
        window.addEventListener('load', sendPageView);
    }
    
    // Track route changes for SPA
    let lastPath = window.location.pathname;
    setInterval(() => {
        if (window.location.pathname !== lastPath) {
            lastPath = window.location.pathname;
            sendPageView();
        }
    }, 1000);
})();
