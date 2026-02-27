// Web Vitals monitoring for AITBC
// Tracks Core Web Vitals: LCP, FID, CLS, TTFB, FCP

(function() {
    'use strict';
    
    function sendToAnalytics(metric) {
        const safeValue = Number.isFinite(metric.value) ? Math.round(metric.value) : 0;
        
        // In production we log to console. The /api/web-vitals endpoint was removed 
        // to reduce unnecessary network noise as we are not running a telemetry backend.
        console.log(`[Web Vitals] ${metric.name}: ${safeValue}`);
    }

    // Load web-vitals from CDN
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/web-vitals@3/dist/web-vitals.iife.js'\;
    script.onload = function() {
        if (window.webVitals) {
            window.webVitals.onCLS(sendToAnalytics);
            window.webVitals.onFID(sendToAnalytics);
            window.webVitals.onLCP(sendToAnalytics);
            window.webVitals.onFCP(sendToAnalytics);
            window.webVitals.onTTFB(sendToAnalytics);
        }
    };
    document.head.appendChild(script);
})();
