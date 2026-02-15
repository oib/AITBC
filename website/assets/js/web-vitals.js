// Web Vitals monitoring for AITBC
// Tracks Core Web Vitals: LCP, FID, CLS, TTFB, FCP

(function() {
    'use strict';
    
    function sendToAnalytics(metric) {
        const data = {
            name: metric.name,
            value: Math.round(metric.value),
            id: metric.id,
            delta: Math.round(metric.delta),
            entries: metric.entries.map(e => ({
                name: e.name,
                startTime: e.startTime,
                duration: e.duration
            })),
            url: window.location.href,
            timestamp: new Date().toISOString()
        };
        
        // Send to analytics endpoint
        if (navigator.sendBeacon) {
            navigator.sendBeacon('/api/web-vitals', JSON.stringify(data));
        }
        
        // Also log to console in development
        console.log(`[Web Vitals] ${metric.name}: ${metric.value}`, metric);
    }
    
    // Largest Contentful Paint (LCP)
    function observeLCP() {
        try {
            const observer = new PerformanceObserver((list) => {
                const entries = list.getEntries();
                const lastEntry = entries[entries.length - 1];
                sendToAnalytics({
                    name: 'LCP',
                    value: lastEntry.renderTime || lastEntry.loadTime,
                    id: lastEntry.id,
                    delta: 0,
                    entries: entries
                });
            });
            observer.observe({ entryTypes: ['largest-contentful-paint'] });
        } catch (e) {}
    }
    
    // First Input Delay (FID)
    function observeFID() {
        try {
            const observer = new PerformanceObserver((list) => {
                const entries = list.getEntries();
                entries.forEach(entry => {
                    sendToAnalytics({
                        name: 'FID',
                        value: entry.processingStart - entry.startTime,
                        id: entry.id,
                        delta: 0,
                        entries: [entry]
                    });
                });
            });
            observer.observe({ entryTypes: ['first-input'] });
        } catch (e) {}
    }
    
    // Cumulative Layout Shift (CLS)
    function observeCLS() {
        try {
            let clsValue = 0;
            const observer = new PerformanceObserver((list) => {
                try {
                    const entries = list.getEntries();
                    entries.forEach(entry => {
                        if (!entry.hadRecentInput) {
                            clsValue += entry.value;
                        }
                    });
                    sendToAnalytics({
                        name: 'CLS',
                        value: clsValue,
                        id: 'cls',
                        delta: 0,
                        entries: entries
                    });
                } catch (e) {
                    // CLS measurement failed, but don't crash the whole script
                    console.log('CLS measurement error:', e.message);
                }
            });
            
            // Try to observe layout-shift, but handle if it's not supported
            try {
                observer.observe({ entryTypes: ['layout-shift'] });
            } catch (e) {
                console.log('Layout-shift observation not supported:', e.message);
                // CLS will not be measured, but other metrics will still work
            }
        } catch (e) {
            console.log('CLS observer setup failed:', e.message);
        }
    }
    
    // Time to First Byte (TTFB)
    function measureTTFB() {
        try {
            const nav = performance.getEntriesByType('navigation')[0];
            if (nav) {
                sendToAnalytics({
                    name: 'TTFB',
                    value: nav.responseStart,
                    id: 'ttfb',
                    delta: 0,
                    entries: [nav]
                });
            }
        } catch (e) {}
    }
    
    // First Contentful Paint (FCP)
    function observeFCP() {
        try {
            const observer = new PerformanceObserver((list) => {
                const entries = list.getEntries();
                entries.forEach(entry => {
                    if (entry.name === 'first-contentful-paint') {
                        sendToAnalytics({
                            name: 'FCP',
                            value: entry.startTime,
                            id: entry.id,
                            delta: 0,
                            entries: [entry]
                        });
                    }
                });
            });
            observer.observe({ entryTypes: ['paint'] });
        } catch (e) {}
    }
    
    // Initialize when page loads
    if (document.readyState === 'complete') {
        observeLCP();
        observeFID();
        observeCLS();
        observeFCP();
        measureTTFB();
    } else {
        window.addEventListener('load', () => {
            observeLCP();
            observeFID();
            observeCLS();
            observeFCP();
            measureTTFB();
        });
    }
})();
