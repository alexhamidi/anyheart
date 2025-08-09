// Background script for Lemur extension

// Handle screenshot requests
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'takeScreenshot') {
        // Take screenshot of the visible tab
        chrome.tabs.captureVisibleTab(null, {format: 'png'}, (dataUrl) => {
            if (chrome.runtime.lastError) {
                console.error('Screenshot error:', chrome.runtime.lastError);
                sendResponse({success: false, error: chrome.runtime.lastError.message});
            } else {
                sendResponse({success: true, screenshot: dataUrl});
            }
        });
        return true; // Keep message channel open for async response
    }
});

