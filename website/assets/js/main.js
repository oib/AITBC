// Smooth scrolling for navigation links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const targetId = this.getAttribute('href');
        if (targetId && targetId !== '#') {
            const targetElement = document.querySelector(targetId);
            if (targetElement) {
                targetElement.scrollIntoView({
                    behavior: 'smooth'
                });
            }
        }
    });
});

// Add animation on scroll
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver(function(entries) {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
        }
    });
}, observerOptions);

// Observe all feature cards
document.querySelectorAll('.feature-card, .arch-component').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
    observer.observe(el);
});

// Dark mode functionality with enhanced persistence and system preference detection
function toggleDarkMode() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
}

function setTheme(theme) {
    // Apply theme immediately
    document.documentElement.setAttribute('data-theme', theme);
    
    // Save to localStorage for persistence
    localStorage.setItem('theme', theme);
    
    // Update button display if it exists
    updateThemeButton(theme);
    
    // Send analytics event
    if (window.analytics) {
        window.analytics.track('theme_changed', { theme });
    }
}

function updateThemeButton(theme) {
    const emoji = document.getElementById('darkModeEmoji');
    const text = document.getElementById('darkModeText');
    
    if (emoji && text) {
        if (theme === 'dark') {
            emoji.textContent = '🌙';
            text.textContent = 'Dark';
        } else {
            emoji.textContent = '☀️';
            text.textContent = 'Light';
        }
    }
}

function getPreferredTheme() {
    // 1. Check localStorage first (user preference)
    const saved = localStorage.getItem('theme');
    if (saved) {
        return saved;
    }
    
    // 2. Check system preference
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        return 'dark';
    }
    
    // 3. Default to dark (AITBC brand preference)
    return 'dark';
}

function initializeTheme() {
    const theme = getPreferredTheme();
    setTheme(theme);
    
    // Listen for system preference changes
    if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            // Only auto-switch if user hasn't manually set a preference
            if (!localStorage.getItem('theme')) {
                setTheme(e.matches ? 'dark' : 'light');
            }
        });
    }
}

// Initialize theme immediately (before DOM loads)
initializeTheme();

// Touch gesture support for mobile navigation
class TouchNavigation {
    constructor() {
        this.touchStartX = 0;
        this.touchStartY = 0;
        this.touchEndX = 0;
        this.touchEndY = 0;
        this.minSwipeDistance = 50;
        this.maxVerticalDistance = 100;
        
        // Get all major sections for navigation
        this.sections = ['hero', 'features', 'architecture', 'achievements', 'documentation'];
        this.currentSectionIndex = 0;
        
        this.bindEvents();
        this.setupMobileOptimizations();
    }
    
    bindEvents() {
        document.addEventListener('touchstart', this.handleTouchStart.bind(this), { passive: false });
        document.addEventListener('touchmove', this.handleTouchMove.bind(this), { passive: false });
        document.addEventListener('touchend', this.handleTouchEnd.bind(this), { passive: false });
    }
    
    handleTouchStart(e) {
        this.touchStartX = e.touches[0].clientX;
        this.touchStartY = e.touches[0].clientY;
    }
    
    handleTouchMove(e) {
        // Prevent scrolling when detecting horizontal swipes
        const touchCurrentX = e.touches[0].clientX;
        const touchCurrentY = e.touches[0].clientY;
        const deltaX = Math.abs(touchCurrentX - this.touchStartX);
        const deltaY = Math.abs(touchCurrentY - this.touchStartY);
        
        // If horizontal movement is greater than vertical, prevent default scrolling
        if (deltaX > deltaY && deltaX > 10) {
            e.preventDefault();
        }
    }
    
    handleTouchEnd(e) {
        this.touchEndX = e.changedTouches[0].clientX;
        this.touchEndY = e.changedTouches[0].clientY;
        
        const deltaX = this.touchEndX - this.touchStartX;
        const deltaY = Math.abs(this.touchEndY - this.touchStartY);
        
        // Only process swipe if vertical movement is minimal
        if (deltaY < this.maxVerticalDistance && Math.abs(deltaX) > this.minSwipeDistance) {
            if (deltaX > 0) {
                this.swipeRight();
            } else {
                this.swipeLeft();
            }
        }
    }
    
    swipeLeft() {
        // Navigate to next section
        const nextIndex = Math.min(this.currentSectionIndex + 1, this.sections.length - 1);
        this.navigateToSection(nextIndex);
    }
    
    swipeRight() {
        // Navigate to previous section
        const prevIndex = Math.max(this.currentSectionIndex - 1, 0);
        this.navigateToSection(prevIndex);
    }
    
    navigateToSection(index) {
        const sectionId = this.sections[index];
        const element = document.getElementById(sectionId);
        
        if (element) {
            this.currentSectionIndex = index;
            element.scrollIntoView({ 
                behavior: 'smooth',
                block: 'start'
            });
            
            // Update URL hash without triggering scroll
            history.replaceState(null, null, `#${sectionId}`);
        }
    }
    
    setupMobileOptimizations() {
        // Add touch-friendly interactions
        this.setupTouchButtons();
        this.setupScrollOptimizations();
        this.setupMobileMenu();
    }
    
    setupTouchButtons() {
        // Make buttons more touch-friendly
        const buttons = document.querySelectorAll('button, .cta-button, .nav-button');
        buttons.forEach(button => {
            button.addEventListener('touchstart', () => {
                button.style.transform = 'scale(0.98)';
            }, { passive: true });
            
            button.addEventListener('touchend', () => {
                button.style.transform = '';
            }, { passive: true });
        });
    }
    
    setupScrollOptimizations() {
        // Improve momentum scrolling on iOS
        if ('webkitOverflowScrolling' in document.body.style) {
            document.body.style.webkitOverflowScrolling = 'touch';
        }
        
        // Add smooth scrolling for anchor links with touch feedback
        document.querySelectorAll('a[href^="#"]').forEach(link => {
            link.addEventListener('touchstart', () => {
                link.style.opacity = '0.7';
            }, { passive: true });
            
            link.addEventListener('touchend', () => {
                link.style.opacity = '';
            }, { passive: true });
        });
    }
    
    setupMobileMenu() {
        // Create mobile menu toggle if nav is hidden on mobile
        const nav = document.querySelector('nav');
        if (nav && window.innerWidth < 768) {
            this.createMobileMenu();
        }
    }
    
    createMobileMenu() {
        // Create hamburger menu for mobile
        const header = document.querySelector('header');
        if (!header) return;
        
        const mobileMenuBtn = document.createElement('button');
        mobileMenuBtn.className = 'mobile-menu-btn';
        mobileMenuBtn.innerHTML = '☰';
        mobileMenuBtn.setAttribute('aria-label', 'Toggle mobile menu');
        
        const nav = document.querySelector('nav');
        if (nav) {
            nav.style.display = 'none';
            
            mobileMenuBtn.addEventListener('click', () => {
                const isOpen = nav.style.display !== 'none';
                nav.style.display = isOpen ? 'none' : 'flex';
                mobileMenuBtn.innerHTML = isOpen ? '☰' : '✕';
            });
            
            // Close menu when clicking outside
            document.addEventListener('click', (e) => {
                if (!header.contains(e.target)) {
                    nav.style.display = 'none';
                    mobileMenuBtn.innerHTML = '☰';
                }
            });
            
            header.appendChild(mobileMenuBtn);
        }
    }
    
    updateCurrentSection() {
        // Update current section based on scroll position
        const scrollY = window.scrollY + window.innerHeight / 2;
        
        this.sections.forEach((sectionId, index) => {
            const element = document.getElementById(sectionId);
            if (element) {
                const rect = element.getBoundingClientRect();
                const elementTop = rect.top + window.scrollY;
                const elementBottom = elementTop + rect.height;
                
                if (scrollY >= elementTop && scrollY < elementBottom) {
                    this.currentSectionIndex = index;
                }
            }
        });
    }
}

// Initialize touch navigation when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new TouchNavigation();
    
    // Update current section on scroll
    window.addEventListener('scroll', () => {
        if (window.touchNav) {
            window.touchNav.updateCurrentSection();
        }
    }, { passive: true });
});
