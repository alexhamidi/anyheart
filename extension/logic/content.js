// Enhanced content script with AI agent observer capabilities and HTML persistence

// Get backend URL - matches constants.js
const getBackendURL = () => {
    // return "https://anyheart.onrender.com"; // Production
    return "http://localhost:8008"; // Development
};

// HTML Persistence Manager
class HTMLPersistenceManager {
    constructor() {
        this.storageKey = this.getStorageKey();
        this.originalHTML = null;
        this.isRestored = false;
    }

    getStorageKey() {
        // Create a unique key based on the current URL (without query params for consistency)
        const url = new URL(window.location.href);
        return `lemur_html_${url.origin}${url.pathname}`;
    }

    async saveCurrentHTML() {
        // Debounce saves to prevent excessive storage operations
        if (this.saveTimeout) {
            clearTimeout(this.saveTimeout);
        }

        this.saveTimeout = setTimeout(async () => {
            try {
                const currentHTML = document.documentElement.outerHTML;
                const data = {
                    html: currentHTML,
                    url: window.location.href,
                    timestamp: Date.now(),
                    title: document.title
                };

                await chrome.storage.local.set({
                    [this.storageKey]: data
                });

                // HTML changes saved to storage
            } catch (error) {
                console.error('Error saving HTML to storage:', error);
            }
        }, 500); // 500ms debounce
    }

    async restoreHTML() {
        try {
            const result = await chrome.storage.local.get(this.storageKey);
            const data = result[this.storageKey];

            if (data && data.html) {
                // Check if the cached version is not too old (24 hours)
                const maxAge = 24 * 60 * 60 * 1000; // 24 hours in milliseconds
                if (Date.now() - data.timestamp < maxAge) {
                    // Restoring cached HTML changes

                    // Store original HTML before restoring
                    this.originalHTML = document.documentElement.outerHTML;

                    // Restore the cached HTML
                    document.documentElement.innerHTML = data.html;
                    this.isRestored = true;

                    // HTML restored from cache
                    return true;
                } else {
                    // Cached HTML is too old, removing from storage
                    await this.clearCache();
                }
            }
        } catch (error) {
            console.error('Error restoring HTML from storage:', error);
        }
        return false;
    }

    async clearCache() {
        try {
            await chrome.storage.local.remove(this.storageKey);
            // Cleared cached HTML for current page
        } catch (error) {
            console.error('Error clearing HTML cache:', error);
        }
    }

    async cleanupOldCache() {
        try {
            const allData = await chrome.storage.local.get(null);
            const maxAge = 7 * 24 * 60 * 60 * 1000; // 7 days
            const keysToRemove = [];

            for (const [key, data] of Object.entries(allData)) {
                if (key.startsWith('lemur_html_') && data.timestamp) {
                    if (Date.now() - data.timestamp > maxAge) {
                        keysToRemove.push(key);
                    }
                }
            }

            if (keysToRemove.length > 0) {
                await chrome.storage.local.remove(keysToRemove);
                // Cleaned up old cached HTML entries
            }
        } catch (error) {
            console.error('Error cleaning up old cache:', error);
        }
    }
}

// Initialize persistence manager
const persistenceManager = new HTMLPersistenceManager();

// Prevent multiple initializations
if (window.lemurContentScriptInitialized) {
    // Content script already initialized, skipping
} else {
    window.lemurContentScriptInitialized = true;

    class AgentObserver {
        constructor(sessionId) {
            this.sessionId = sessionId;
            this.isObserving = false;
            this.observationTimeout = null;
        }

        async startObservation() {
            this.isObserving = true;

            // Wait a bit for page to stabilize after changes
            await new Promise(resolve => setTimeout(resolve, 1500));

            // Check if we should still be observing
            if (!this.isObserving) {
                // Observation cancelled
                return;
            }

            try {
                // Take screenshot first
                const screenshot = await this.takeScreenshot();

                // Gather comprehensive observation data
                const observation = {
                    summary: this.generateSummary(),
                    error_occurred: this.checkForErrors(),
                    error_message: this.getErrorMessage(),
                    visual_change_score: this.calculateVisualChange(),
                    performance_metrics: this.gatherPerformanceMetrics(),
                    screenshot: screenshot,
                    timestamp: new Date().toISOString()
                };

                // Submitting observation to agent

                // Submit observation via WebSocket through popup
                // Send observation via POST request to backend
                if (window.sendObservation) {
                    window.sendObservation(observation);
                } else {
                    // Fallback: send message to popup for POST request
                    chrome.runtime.sendMessage({
                        action: 'sendObservation',
                        data: observation
                    });
                }

                return { success: true };
            } catch (error) {
                console.error('Error submitting observation:', error);
                return { success: false, error: error.message };
            }
        }

        async takeScreenshot() {
            try {
                // Request screenshot from background script
                const response = await new Promise((resolve) => {
                    chrome.runtime.sendMessage({ action: 'takeScreenshot' }, resolve);
                });
                return response?.screenshot || null;
            } catch (error) {
                console.error('Error taking screenshot:', error);
                return null;
            }
        }

        generateSummary() {
            const elements = document.querySelectorAll('*');
            const visibleElements = Array.from(elements).filter(el => {
                const style = window.getComputedStyle(el);
                return style.display !== 'none' && style.visibility !== 'hidden';
            });

            return `Page has ${elements.length} total elements, ${visibleElements.length} visible. ` +
                `Title: "${document.title}". ` +
                `Main content areas: ${this.identifyMainAreas()}`;
        }

        identifyMainAreas() {
            const areas = [];
            if (document.querySelector('header')) areas.push('header');
            if (document.querySelector('nav')) areas.push('nav');
            if (document.querySelector('main')) areas.push('main');
            if (document.querySelector('aside')) areas.push('aside');
            if (document.querySelector('footer')) areas.push('footer');
            return areas.join(', ') || 'no semantic areas';
        }

        checkForErrors() {
            // Check for JavaScript errors
            const errors = window.lemurErrors || [];

            // Check for broken images
            const brokenImages = Array.from(document.querySelectorAll('img')).filter(img =>
                !img.complete || img.naturalWidth === 0
            );

            // Check for missing resources
            const missingResources = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).filter(link =>
                !link.sheet
            );

            return errors.length > 0 || brokenImages.length > 0 || missingResources.length > 0;
        }

        getErrorMessage() {
            const errors = [];

            if (window.lemurErrors && window.lemurErrors.length > 0) {
                errors.push(`JS errors: ${window.lemurErrors.length}`);
            }

            const brokenImages = Array.from(document.querySelectorAll('img')).filter(img =>
                !img.complete || img.naturalWidth === 0
            );
            if (brokenImages.length > 0) {
                errors.push(`Broken images: ${brokenImages.length}`);
            }

            return errors.join(', ') || null;
        }

        calculateVisualChange() {
            // Simple heuristic: assume moderate change by default
            // In a real implementation, this could compare screenshots or DOM structure
            return Math.floor(Math.random() * 50) + 25; // 25-75 range
        }

        gatherPerformanceMetrics() {
            const navigation = performance.getEntriesByType('navigation')[0];
            return {
                load_time: navigation ? navigation.loadEventEnd - navigation.loadEventStart : 0,
                dom_elements: document.querySelectorAll('*').length,
                images_count: document.querySelectorAll('img').length,
                stylesheets_count: document.querySelectorAll('link[rel="stylesheet"]').length,
                scripts_count: document.querySelectorAll('script').length,
                viewport_width: window.innerWidth,
                viewport_height: window.innerHeight
            };
        }

        stop() {
            this.isObserving = false;
            if (this.observationTimeout) {
                clearTimeout(this.observationTimeout);
            }
        }
    }

    // Track JavaScript errors for observation
    window.lemurErrors = [];
    window.addEventListener('error', (event) => {
        window.lemurErrors.push({
            message: event.message,
            filename: event.filename,
            lineno: event.lineno,
            timestamp: new Date().toISOString()
        });
    });

    let currentObserver = null;

    // Initialize persistence on page load
    (async function initializePersistence() {
        try {
            // Wait for DOM to be ready
            if (document.readyState === 'loading') {
                await new Promise(resolve => {
                    document.addEventListener('DOMContentLoaded', resolve);
                });
            }

            // Clean up old cache entries periodically
            await persistenceManager.cleanupOldCache();

            // Restore cached HTML if available
            const wasRestored = await persistenceManager.restoreHTML();

            if (wasRestored) {
                console.log('HTML persistence initialized - cached content restored');
            } else {
                console.log('HTML persistence initialized - no cached content found');
            }
        } catch (error) {
            console.error('Error initializing HTML persistence:', error);
        }
    })();

    // Listen for messages from popup
    chrome.runtime.onMessage.addListener(async (request, sender, sendResponse) => {
        if (request.action === 'logText') {
            console.log('Text from Lemur extension:', request.text);
        }

        if (request.action === 'getHTML') {
            const pageHTML = document.documentElement.outerHTML;
            sendResponse({ html: pageHTML });
        }

        if (request.action === 'replace') {
            try {
                document.documentElement.innerHTML = request.newContent;
                console.log('Page replaced with updated content');

                // Save the changes to storage
                await persistenceManager.saveCurrentHTML();
            } catch (error) {
                console.error('Error replacing page content:', error);
            }
        }

        if (request.action === 'applyAgentEdit') {
            try {
                // Stop any existing observer
                if (currentObserver) {
                    currentObserver.stop();
                }

                // Apply the new HTML
                document.documentElement.innerHTML = request.newContent;
                console.log('Applied agent edit, starting observation...');

                // Save the changes to storage
                await persistenceManager.saveCurrentHTML();

                // Start new observer
                currentObserver = new AgentObserver(request.sessionId);

                // Start observation after a delay
                setTimeout(() => {
                    currentObserver.startObservation();
                }, 500);

            } catch (error) {
                console.error('Error applying agent edit:', error);

                // Submit error observation via POST request
                if (request.sessionId && window.sendObservation) {
                    window.sendObservation({
                        summary: 'Failed to apply changes',
                        error_occurred: true,
                        error_message: error.message,
                        timestamp: new Date().toISOString()
                    });
                }
            }
        }

        if (request.action === 'clearCache') {
            try {
                await persistenceManager.clearCache();
                console.log('Cache cleared for current page');
                sendResponse({ success: true });
            } catch (error) {
                console.error('Error clearing cache:', error);
                sendResponse({ success: false, error: error.message });
            }
        }

        if (request.action === 'restoreOriginal') {
            try {
                if (persistenceManager.originalHTML) {
                    document.documentElement.innerHTML = persistenceManager.originalHTML;
                    await persistenceManager.clearCache();
                    console.log('Restored original HTML');
                    sendResponse({ success: true });
                } else {
                    sendResponse({ success: false, error: 'No original HTML available' });
                }
            } catch (error) {
                console.error('Error restoring original HTML:', error);
                sendResponse({ success: false, error: error.message });
            }
        }

        return true;
    });

    // --- URL Sharing: Check for aid parameter and load shared configuration ---
    (async function checkForSharedConfiguration() {
        try {
            // Parse URL parameters
            const urlParams = new URLSearchParams(window.location.search);
            const shareId = urlParams.get('aid');

            if (!shareId) {
                console.log('No aid parameter found, skipping shared configuration check');
                return;
            }

            console.log('Found aid parameter:', shareId, 'attempting to load shared configuration...');

            // Fetch shared configuration from backend
            const response = await fetch(`${getBackendURL()}/api/share/${shareId}`);

            if (!response.ok) {
                if (response.status === 404) {
                    console.warn('Shared configuration not found for ID:', shareId);
                    showShareNotification('Shared configuration not found', 'error');
                    return;
                } else if (response.status === 410) {
                    console.warn('Shared configuration expired for ID:', shareId);
                    showShareNotification('Shared configuration has expired', 'error');
                    return;
                } else {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
            }

            const sharedConfig = await response.json();
            console.log('Retrieved shared configuration:', sharedConfig);

            // Verify this is the correct original URL (basic check)
            const currentUrlWithoutParams = window.location.origin + window.location.pathname;
            const originalUrlWithoutParams = new URL(sharedConfig.original_url).origin + new URL(sharedConfig.original_url).pathname;

            if (currentUrlWithoutParams !== originalUrlWithoutParams) {
                console.warn('URL mismatch - shared config is for different page');
                showShareNotification('This shared configuration is for a different page', 'error');
                return;
            }

            // Store original HTML before applying changes
            persistenceManager.originalHTML = document.documentElement.outerHTML;

            // Apply the shared HTML configuration
            document.documentElement.innerHTML = sharedConfig.modified_html;
            console.log('Applied shared HTML configuration');

            // Show success notification
            showShareNotification(`Loaded shared configuration: "${sharedConfig.title}"`, 'success');

            // Save to local storage so it persists on refresh
            await persistenceManager.saveCurrentHTML();

        } catch (error) {
            console.error('Error loading shared configuration:', error);
            showShareNotification('Failed to load shared configuration', 'error');
        }
    })();

    // Helper function to show share-related notifications
    function showShareNotification(message, type = 'info') {
        // Create a temporary notification element
        const notification = document.createElement('div');
        notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 16px;
        border-radius: 6px;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
                 font-size: 14px;
        font-weight: 500;
        z-index: 10000;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        max-width: 300px;
        word-wrap: break-word;
        transition: opacity 0.3s ease;
    `;

        // Set colors based on type
        if (type === 'error') {
            notification.style.backgroundColor = '#fee2e2';
            notification.style.color = '#dc2626';
            notification.style.border = '1px solid #fecaca';
        } else if (type === 'success') {
            notification.style.backgroundColor = '#dcfce7';
            notification.style.color = '#16a34a';
            notification.style.border = '1px solid #bbf7d0';
        } else {
            notification.style.backgroundColor = '#dbeafe';
            notification.style.color = '#1d4ed8';
            notification.style.border = '1px solid #bfdbfe';
        }

        notification.textContent = message;
        document.body.appendChild(notification);

        // Remove notification after 5 seconds
        setTimeout(() => {
            notification.style.opacity = '0';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 5000);
    }

} // End of initialization check