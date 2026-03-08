/**
 * AITBC Documentation Theme Toggle
 * Handles dark/light mode switching with localStorage persistence
 */

(function() {
    'use strict';

    const STORAGE_KEY = 'aitbc-docs-theme';
    
    // Initialize theme on page load
    function initTheme() {
        const savedTheme = localStorage.getItem(STORAGE_KEY);
        const themeToggle = document.getElementById('theme-toggle');
        
        if (savedTheme === 'light') {
            document.body.classList.add('light');
            if (themeToggle) {
                themeToggle.innerHTML = '<i class="fas fa-moon"></i>';
            }
        }
        
        // Setup toggle button listener
        if (themeToggle) {
            themeToggle.addEventListener('click', toggleTheme);
        }
    }
    
    // Toggle between light and dark themes
    function toggleTheme() {
        const themeToggle = document.getElementById('theme-toggle');
        document.body.classList.toggle('light');
        
        const isLight = document.body.classList.contains('light');
        
        if (themeToggle) {
            themeToggle.innerHTML = isLight 
                ? '<i class="fas fa-moon"></i>' 
                : '<i class="fas fa-sun"></i>';
        }
        
        localStorage.setItem(STORAGE_KEY, isLight ? 'light' : 'dark');
    }
    
    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTheme);
    } else {
        initTheme();
    }
    
    // Expose for manual use if needed
    window.toggleTheme = toggleTheme;
})();
