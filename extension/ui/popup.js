// Enhanced frontend with AI agent polling system

let currentAgentSession = null;
// Using POST requests for agent communication
let conversationHistory = [];
// Session persistence for conversation continuity
let sessionStorageKey = null;

document.addEventListener('DOMContentLoaded', async () => {
  const input = document.getElementById('textInput');
  const resetBtn = document.getElementById('resetBtn');
  const clearCacheBtn = document.getElementById('clearCacheBtn');
  const exportUrlBtn = document.getElementById('exportUrlBtn');

  const conversationMessages = document.getElementById('conversationMessages');
  const statusDiv = createStatusDiv();

  // Initialize session storage key based on current tab
  await initializeSessionStorage();

  // Load existing session if available
  await loadExistingSession();

  // Autofocus the input when the popup opens
  input.focus();

  input.addEventListener('keypress', async (e) => {
    if (e.key === 'Enter') {
      await processInput();
    }
  });

  // Reset button - restore page to original state
  resetBtn.addEventListener('click', async () => {
    try {
      updateStatus('resetting...', 'info');

      const tabs = await new Promise(resolve => {
        chrome.tabs.query({ active: true, currentWindow: true }, resolve);
      });

      const tab = tabs[0];

      // Send reset message to content script
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['logic/content.js']
      });
      await new Promise(resolve => setTimeout(resolve, 200));

      const response = await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          reject(new Error('Content script not responding'));
        }, 5000);

        chrome.tabs.sendMessage(tab.id, { action: 'restoreOriginal' }, (response) => {
          clearTimeout(timeout);
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
          } else {
            resolve(response);
          }
        });
      });

      if (response && response.success) {
        // Reset session and clear conversation
        await resetSession();
      } else {
        updateStatus('reset failed', 'error');
      }

    } catch (error) {
      console.error('Error resetting page:', error);
      updateStatus('error', 'error');
    }
  });



  // Clear all local storage
  clearCacheBtn.addEventListener('click', async () => {
    try {
      // Clear all extension local storage
      await chrome.storage.local.clear();

      updateStatus('cleared', 'success');
      console.log('All extension local storage has been cleared');
    } catch (error) {
      console.error('Error clearing local storage:', error);
      updateStatus('error', 'error');
    }
  });

  // Export URL functionality
  exportUrlBtn.addEventListener('click', async () => {
    try {
      updateStatus('creating...', 'info');

      const tabs = await new Promise(resolve => {
        chrome.tabs.query({ active: true, currentWindow: true }, resolve);
      });

      const tab = tabs[0];

      // Get current HTML state from content script
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['logic/content.js']
      });
      await new Promise(resolve => setTimeout(resolve, 200));

      const response = await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          reject(new Error('Content script not responding'));
        }, 5000);

        chrome.tabs.sendMessage(tab.id, { action: 'getHTML' }, (response) => {
          clearTimeout(timeout);
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
          } else {
            resolve(response);
          }
        });
      });

      if (response && response.html) {
        // Create shareable configuration via API
        const shareResponse = await fetch(`${BACKEND_URL}/api/share`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            url: tab.url,
            html: response.html,
            title: tab.title,
            description: `Shared customization of ${tab.title}`,
            expires_in_days: 30
          })
        });

        if (!shareResponse.ok) {
          throw new Error(`HTTP error! status: ${shareResponse.status}`);
        }

        const shareData = await shareResponse.json();

        // Copy shareable URL to clipboard
        await navigator.clipboard.writeText(shareData.shareable_url);

        updateStatus('link copied to clipboard', 'success');

      } else {
        updateStatus('failed', 'error');
      }

    } catch (error) {
      console.error('Error creating shareable URL:', error);
      updateStatus('error', 'error');
    }
  });





  function createStatusDiv() {
    const statusDiv = document.createElement('div');
    statusDiv.id = 'agentStatus';
    statusDiv.style.cssText = `
        padding: 8px 14px;
        background: transparent;
        color: #6b7280;
        border: 1px solid rgba(0, 0, 0, 0.08);
        border-radius: 12px;
        font-size: 13px;
        font-weight: 400;
        font-family: inherit;
        display: none;
        max-width: 100%;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
        text-transform: lowercase;
      `;
    const statusContainer = document.getElementById('statusContainer');
    statusContainer.appendChild(statusDiv);
    return statusDiv;
  }

  function updateStatus(message, type = 'info') {
    statusDiv.style.display = 'block';
    statusDiv.textContent = message.toLowerCase();

    // Minimal theme colors with subtle tints
    if (type === 'error') {
      statusDiv.style.background = 'rgba(220, 38, 38, 0.05)';
      statusDiv.style.color = '#dc2626';
      statusDiv.style.border = '1px solid rgba(220, 38, 38, 0.15)';
      statusDiv.style.boxShadow = '0 1px 2px rgba(220, 38, 38, 0.08)';
    } else if (type === 'success') {
      statusDiv.style.background = 'rgba(22, 163, 74, 0.05)';
      statusDiv.style.color = '#16a34a';
      statusDiv.style.border = '1px solid rgba(22, 163, 74, 0.15)';
      statusDiv.style.boxShadow = '0 1px 2px rgba(22, 163, 74, 0.08)';
    } else {
      statusDiv.style.background = 'transparent';
      statusDiv.style.color = '#6b7280';
      statusDiv.style.border = '1px solid rgba(0, 0, 0, 0.08)';
      statusDiv.style.boxShadow = '0 1px 2px rgba(0, 0, 0, 0.02)';
    }
  }

  function addMessageToConversation(sender, content, type = 'normal') {
    const timestamp = new Date().toLocaleTimeString();
    const message = {
      role: sender, // Use 'role' to match backend format
      content,
      type,
      timestamp
    };

    // Handle system messages differently - send to status instead of conversation
    if (sender.toLowerCase() === 'system') {
      updateStatus(content, 'info');
      return;
    }

    conversationHistory.push(message);
    displayConversation();

    // Save session after adding message
    saveSession();
  }

  function displayConversation() {
    // Filter out system messages - they go to status area instead
    const nonSystemMessages = conversationHistory.filter(message =>
      message.role.toLowerCase() !== 'system'
    );

    if (nonSystemMessages.length === 0) {
      conversationMessages.innerHTML = '<div class="conversation-empty">No conversation yet. Start by entering a query above.</div>';
      return;
    }

    conversationMessages.innerHTML = '';

    // Display user and assistant messages only
    nonSystemMessages.forEach(message => {
      const messageContainer = document.createElement('div');
      messageContainer.className = 'message-container';

      // Create message content with appropriate styling
      const messageContent = document.createElement('div');
      if (message.role.toLowerCase() === 'assistant') {
        messageContent.className = 'message-green';
      } else {
        // User messages get blue styling
        messageContent.className = 'message-blue';
      }

      messageContent.style.fontSize = '14px';
      messageContent.style.lineHeight = '1.4';
      messageContent.style.whiteSpace = 'pre-wrap';
      messageContent.style.wordWrap = 'break-word';
      messageContent.style.color = '#1a1a1a';
      messageContent.textContent = message.content;

      messageContainer.appendChild(messageContent);
      conversationMessages.appendChild(messageContainer);
    });

    // Scroll to bottom
    conversationMessages.scrollTop = conversationMessages.scrollHeight;
  }

  function clearConversation() {
    conversationHistory = [];
    displayConversation();
  }

  async function processInput() {
    // Get page content first
    const tabs = await new Promise(resolve => {
      chrome.tabs.query({ active: true, currentWindow: true }, resolve);
    });

    const tab = tabs[0];

    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ['logic/content.js']
    });
    await new Promise(resolve => setTimeout(resolve, 200));

    // Now send the message
    const response = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Content script not responding. The page may not support this extension.'));
      }, 5000);

      chrome.tabs.sendMessage(tab.id, {
        action: 'getHTML'
      }, (response) => {
        clearTimeout(timeout);
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve(response);
        }
      });
    });

    if (response && response.html) {
      // Got page HTML for agent processing

      const userPrompt = input.value;

      // Check if we have an existing session
      if (currentAgentSession) {
        // Continue existing conversation
        // Continuing existing session
        addMessageToConversation('User', userPrompt);

        // Clear input
        input.value = '';

        // Send user request to existing session
        await sendUserRequest(currentAgentSession, userPrompt);
        return;
      }

      // No existing session - create new one
      addMessageToConversation('User', userPrompt);

      updateStatus('capturing initial state...');

      // Take initial screenshot before starting agent session
      let initialScreenshot = null;
      try {
        const screenshotResponse = await new Promise((resolve, reject) => {
          chrome.runtime.sendMessage({ action: 'takeScreenshot' }, (response) => {
            if (chrome.runtime.lastError) {
              reject(new Error(chrome.runtime.lastError.message));
            } else {
              resolve(response);
            }
          });
        });

        if (screenshotResponse.success && screenshotResponse.screenshot) {
          initialScreenshot = screenshotResponse.screenshot;
          // Captured initial screenshot for agent context
        }
      } catch (error) {
        console.error('Error taking initial screenshot:', error);
        // Continue without screenshot - don't fail the entire process
      }

      updateStatus('starting...');

      try {
        // Start agent session with initial screenshot
        const sessionResponse = await fetch(`${BACKEND_URL}/agent/start`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            query: input.value,
            html: response.html,
            initial_screenshot: initialScreenshot,
            model_type: 'gemini'
          })
        });

        if (!sessionResponse.ok) {
          throw new Error(`HTTP error! status: ${sessionResponse.status}`);
        }

        const sessionData = await sessionResponse.json();
        currentAgentSession = sessionData.session_id;

        updateStatus('connected');

        // Clear input
        input.value = '';

        // Initialize session with POST requests
        initializeSession(tab.id, sessionData.session_id);

        // Save the new session
        await saveSession();

        // Send the initial user query
        await sendUserRequest(sessionData.session_id, userPrompt, initialScreenshot);

      } catch (error) {
        console.error('Error starting agent session:', error);
        updateStatus('error', 'error');
      }
    }
  }

  // Initialize agent session via POST requests
  function initializeSession(tabId, sessionId) {
    // Session initialized successfully
    updateStatus('ready');

    // Store session info for later use
    window.currentTabId = tabId;
    window.currentSessionId = sessionId;
  }

  // Send user request via POST
  async function sendUserRequest(sessionId, query, screenshot = null) {
    try {
      updateStatus('processing', 'info');

      const response = await fetch(`${BACKEND_URL}/agent/${sessionId}/request`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: query,
          screenshot: screenshot
        })
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || 'Request failed');
      }

      // Handle successful response
      if (result.updated_html) {
        // Apply HTML changes to the page
        chrome.tabs.sendMessage(window.currentTabId, {
          action: 'applyAgentEdit',
          newContent: result.updated_html,
          sessionId: sessionId
        });
        addMessageToConversation('System', 'Applied HTML changes to page');
      }

      // Add assistant response to conversation
      addMessageToConversation('Assistant', result.message);
      updateStatus('ready');

    } catch (error) {
      console.error('Error sending user request:', error);
      addMessageToConversation('System', `Error: ${error.message}`, 'error');
      updateStatus('error', 'error');
    }
  }

  // --- send follow-up user request ---
  window.sendObservation = function (observationData) {
    if (window.currentSessionId && observationData.query) {
      // Send as a new user request
      sendUserRequest(window.currentSessionId, observationData.query, observationData.screenshot);
    }
  };

  // --- listen for messages from content script ---
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'sendObservation') {
      // Forward observation as a new user request
      if (window.currentSessionId && request.data.query) {
        sendUserRequest(window.currentSessionId, request.data.query, request.data.screenshot);
        // Forwarded observation from content script
      }
    }
  });

  // === SESSION MANAGEMENT FUNCTIONS ===

  async function initializeSessionStorage() {
    try {
      const tabs = await new Promise(resolve => {
        chrome.tabs.query({ active: true, currentWindow: true }, resolve);
      });

      const tab = tabs[0];
      const url = new URL(tab.url);
      sessionStorageKey = `anyheart_session_${url.origin}${url.pathname}`;
      // Session storage key generated
    } catch (error) {
      console.error('Error initializing session storage:', error);
      sessionStorageKey = 'anyheart_session_default';
    }
  }

  async function loadExistingSession() {
    try {
      if (!sessionStorageKey) return;

      const result = await chrome.storage.local.get(sessionStorageKey);
      const sessionData = result[sessionStorageKey];

      if (sessionData && sessionData.sessionId) {
        // Found stored session

        // Validate session still exists on backend
        try {
          const response = await fetch(`${BACKEND_URL}/agent/${sessionData.sessionId}/status`);

          if (response.ok) {
            const backendSession = await response.json();
            // Session validated on backend

            // Restore session state
            currentAgentSession = sessionData.sessionId;
            conversationHistory = sessionData.conversationHistory || [];

            // Restore UI
            displayConversationHistory();
            updateStatus('ready');

            // Store session info for later use
            window.currentSessionId = sessionData.sessionId;
          } else {
            // Session no longer exists on backend, clearing local storage
            await chrome.storage.local.remove(sessionStorageKey);
          }
        } catch (error) {
          // Error validating session on backend, clearing local storage
          await chrome.storage.local.remove(sessionStorageKey);
        }
      }
    } catch (error) {
      console.error('Error loading existing session:', error);
    }
  }

  async function saveSession() {
    try {
      if (!sessionStorageKey || !currentAgentSession) return;

      const sessionData = {
        sessionId: currentAgentSession,
        conversationHistory: conversationHistory,
        timestamp: Date.now()
      };

      await chrome.storage.local.set({
        [sessionStorageKey]: sessionData
      });

      console.log('Session saved:', currentAgentSession);
    } catch (error) {
      console.error('Error saving session:', error);
    }
  }

  async function resetSession() {
    try {
      // Clear session storage
      if (sessionStorageKey) {
        await chrome.storage.local.remove(sessionStorageKey);
      }

      // Reset local state
      currentAgentSession = null;
      conversationHistory = [];
      window.currentSessionId = null;

      // Clear UI
      clearConversation();
      updateStatus('reset complete', 'success');

      console.log('Session reset complete');
    } catch (error) {
      console.error('Error resetting session:', error);
    }
  }

  function displayConversationHistory() {
    // Clear existing messages
    conversationMessages.innerHTML = '';

    // Display each message in the history
    conversationHistory.forEach(msg => {
      addMessageToConversation(msg.role, msg.content, msg.type || 'normal');
    });
  }

});