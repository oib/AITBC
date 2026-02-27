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

// Touch gesture support for mobile navigation
class TouchNavigation {
    constructor() {
        this.touchStartX = 0;
        this.touchStartY = 0;
        this.touchEndX = 0;
        this.touchEndY = 0;
        this.minSwipeDistance = 50;
        this.maxVerticalDistance = 100;

        this.initializeTouchEvents();
    }

    initializeTouchEvents() {
        document.addEventListener('touchstart', (e) => {
            this.touchStartX = e.changedTouches[0].screenX;
            this.touchStartY = e.changedTouches[0].screenY;
        }, { passive: true });

        document.addEventListener('touchend', (e) => {
            this.touchEndX = e.changedTouches[0].screenX;
            this.touchEndY = e.changedTouches[0].screenY;
            this.handleSwipe();
        }, { passive: true });
    }

    handleSwipe() {
        const xDiff = this.touchEndX - this.touchStartX;
        const yDiff = Math.abs(this.touchEndY - this.touchStartY);

        // Ensure swipe is mostly horizontal
        if (yDiff > this.maxVerticalDistance) return;

        if (Math.abs(xDiff) > this.minSwipeDistance) {
            if (xDiff > 0) {
                // Swipe Right - potentially open menu or go back
                this.onSwipeRight();
            } else {
                // Swipe Left - potentially close menu or go forward
                this.onSwipeLeft();
            }
        }
    }

    onSwipeRight() {
        // Can be implemented if a side menu is added
        // console.log('Swiped right');
    }

    onSwipeLeft() {
        // Can be implemented if a side menu is added
        // console.log('Swiped left');
    }
}

// Initialize touch navigation when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new TouchNavigation();
});
