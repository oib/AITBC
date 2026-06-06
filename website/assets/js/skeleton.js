/**
 * Skeleton Loading States for AITBC Website
 * Provides loading placeholders while content is being fetched
 */

class SkeletonLoader {
    constructor() {
        this.skeletonStyles = `
            .skeleton {
                background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
                background-size: 200% 100%;
                animation: skeleton-loading 1.5s infinite;
                border-radius: 4px;
            }
            
            @keyframes skeleton-loading {
                0% { background-position: 200% 0; }
                100% { background-position: -200% 0; }
            }
            
            .skeleton-text {
                height: 1rem;
                margin-bottom: 0.5rem;
            }
            
            .skeleton-text.title {
                height: 2rem;
                width: 60%;
            }
            
            .skeleton-text.subtitle {
                height: 1.2rem;
                width: 40%;
            }
            
            .skeleton-card {
                height: 120px;
                margin-bottom: 1rem;
            }
            
            .skeleton-button {
                height: 2.5rem;
                width: 120px;
                border-radius: 6px;
            }
            
            .dark .skeleton {
                background: linear-gradient(90deg, #374151 25%, #4b5563 50%, #374151 75%);
                background-size: 200% 100%;
            }
        `;
        
        this.init();
    }
    
    init() {
        // Inject skeleton styles
        if (!document.getElementById('skeleton-styles')) {
            const style = document.createElement('style');
            style.id = 'skeleton-styles';
            style.textContent = this.skeletonStyles;
            document.head.appendChild(style);
        }
    }
    
    // Create skeleton element
    createSkeleton(type = 'text', customClass = '') {
        const skeleton = document.createElement('div');
        skeleton.className = `skeleton skeleton-${type} ${customClass}`;
        return skeleton;
    }
    
    // Show skeleton for a container
    showSkeleton(container, config = {}) {
        const {
            type = 'text',
            count = 3,
            customClass = ''
        } = config;
        
        // Store original content
        const originalContent = container.innerHTML;
        container.dataset.originalContent = originalContent;
        
        // Clear and add skeletons
        container.innerHTML = '';
        for (let i = 0; i < count; i++) {
            container.appendChild(this.createSkeleton(type, customClass));
        }
    }
    
    // Hide skeleton and restore content
    hideSkeleton(container, content = null) {
        if (content) {
            container.innerHTML = content;
        } else if (container.dataset.originalContent) {
            container.innerHTML = container.dataset.originalContent;
            delete container.dataset.originalContent;
        }
    }
    
    // Marketplace specific skeletons
    showMarketplaceSkeletons() {
        const statsContainer = document.querySelector('#stats-container');
        const offersContainer = document.querySelector('#offers-container');
        
        if (statsContainer) {
            this.showSkeleton(statsContainer, {
                type: 'card',
                count: 4,
                customClass: 'stats-skeleton'
            });
        }
        
        if (offersContainer) {
            this.showSkeleton(offersContainer, {
                type: 'card',
                count: 6,
                customClass: 'offer-skeleton'
            });
        }
    }
}

// Initialize skeleton loader
window.skeletonLoader = new SkeletonLoader();

// Auto-hide skeletons when content is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Hide skeletons after a timeout as fallback
    setTimeout(() => {
        document.querySelectorAll('.skeleton').forEach(skeleton => {
            const container = skeleton.parentElement;
            if (container && container.dataset.originalContent) {
                window.skeletonLoader.hideSkeleton(container);
            }
        });
    }, 5000);
});
