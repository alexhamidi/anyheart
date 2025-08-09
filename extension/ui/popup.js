// Enhanced frontend with AI agent polling system

let currentAgentSession = null;
let agentWebSocket = null;
let conversationHistory = [];
let isCapturingActive = false;
let captureInterval = null;
let mostRecentUserPrompt = null;

document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('textInput');
  const stalkerModeBtn = document.getElementById('stalkerModeBtn');
  const clearCacheBtn = document.getElementById('clearCacheBtn');
  const exportUrlBtn = document.getElementById('exportUrlBtn');

  const conversationMessages = document.getElementById('conversationMessages');
  const statusDiv = createStatusDiv();

  // Autofocus the input when the popup opens
  input.focus();

  input.addEventListener('keypress', async (e) => {
    if (e.key === 'Enter') {
      await processInput();
    }
  });

  // Capture button - toggle capture mode
  stalkerModeBtn.addEventListener('click', async () => {
    if (!isCapturingActive) {
      // Start capturing
      isCapturingActive = true;
      stalkerModeBtn.textContent = 'Stop';
      stalkerModeBtn.classList.add('active');
      stalkerModeBtn.title = 'Stop Capture Mode';

      updateStatus('Capture mode started - taking screenshots every 5 seconds', 'info');

      // Take initial screenshot
      await takeScreenshot();

      // Set up interval for continuous screenshots
      captureInterval = setInterval(async () => {
        await takeScreenshot();
      }, 5000); // Take screenshot every 5 seconds

    } else {
      // Stop capturing
      isCapturingActive = false;
      stalkerModeBtn.textContent = 'Capture';
      stalkerModeBtn.classList.remove('active');
      stalkerModeBtn.title = 'Capture Mode';

      if (captureInterval) {
        clearInterval(captureInterval);
        captureInterval = null;
      }

      updateStatus('Capture mode stopped', 'success');
    }
  });

  async function takeScreenshot() {
    try {
      // Request screenshot from background script
      const response = await new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({ action: 'takeScreenshot' }, (response) => {
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
          } else {
            resolve(response);
          }
        });
      });

      if (response.success && response.screenshot) {
        // Convert data URL to blob
        const response_data = await fetch(response.screenshot);
        const blob = await response_data.blob();

        // Create download link
        const url = URL.createObjectURL(blob);
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = `capture-screenshot-${timestamp}.png`;

        // Trigger download
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        if (isCapturingActive) {
          updateStatus(`Capture active - Screenshot saved as ${filename}`, 'info');
        } else {
          updateStatus(`Screenshot saved as ${filename}`, 'success');
        }
      } else {
        updateStatus('Failed to take screenshot', 'error');
      }
    } catch (error) {
      console.error('Error taking screenshot:', error);
      updateStatus('Error taking screenshot: ' + error.message, 'error');
    }
  }

  // Clear all local storage
  clearCacheBtn.addEventListener('click', async () => {
    try {
      // Clear all extension local storage
      await chrome.storage.local.clear();

      updateStatus('all local storage cleared', 'success');
      console.log('All extension local storage has been cleared');
    } catch (error) {
      console.error('Error clearing local storage:', error);
      updateStatus('error clearing local storage', 'error');
    }
  });

  // Export URL functionality
  exportUrlBtn.addEventListener('click', async () => {
    try {
      updateStatus('Creating shareable URL...', 'info');

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
        const shareResponse = await fetch('http://localhost:8008/api/share', {
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
        updateStatus('Could not get page content', 'error');
      }

    } catch (error) {
      console.error('Error creating shareable URL:', error);
      updateStatus(`Error creating shareable URL: ${error.message}`, 'error');
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
        font-size: 11px;
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
      sender,
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
  }

  function displayConversation() {
    // Filter out system messages - they go to status area instead
    const nonSystemMessages = conversationHistory.filter(message =>
      message.sender.toLowerCase() !== 'system'
    );

    if (nonSystemMessages.length === 0) {
      conversationMessages.innerHTML = '<div class="conversation-empty">No conversation yet. Start by entering a query above.</div>';
      return;
    }

    conversationMessages.innerHTML = '';

    // Display user and assistant messages only
    nonSystemMessages.forEach(message => {
      const messageDiv = document.createElement('div');
      messageDiv.className = 'message-glow-container';

      // Create glow container with appropriate color
      const glowContainer = document.createElement('div');
      glowContainer.className = 'message-glow-container';

      if (message.sender.toLowerCase() === 'assistant') {
        glowContainer.classList.add('message-glow-green');
      } else {
        // User messages get blue glow
        glowContainer.classList.add('message-glow-blue');
      }

      // Create inner content container
      const innerDiv = document.createElement('div');
      innerDiv.className = 'message-inner';
      innerDiv.textContent = message.content;

      glowContainer.appendChild(innerDiv);
      messageDiv.appendChild(glowContainer);

      conversationMessages.appendChild(messageDiv);
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
      console.log('Got page HTML, length:', response.html.length);

      // Clear previous conversation and start fresh
      clearConversation();

      // Add user message to conversation
      const userPrompt = input.value;
      addMessageToConversation('User', userPrompt);

      updateStatus('Starting AI agent session...');

      try {
        // Start agent session
        const sessionResponse = await fetch('http://localhost:8008/agent/start', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            query: input.value,
            html: response.html,
            model_type: 'gemini'
          })
        });

        if (!sessionResponse.ok) {
          throw new Error(`HTTP error! status: ${sessionResponse.status}`);
        }

        const sessionData = await sessionResponse.json();
        currentAgentSession = sessionData.session_id;

        updateStatus(`Agent session started: ${currentAgentSession.substring(0, 8)}...`);

        // Clear input
        input.value = '';

        // Connect WebSocket
        connectWebSocket(tab.id, sessionData.session_id);

      } catch (error) {
        console.error('Error starting agent session:', error);
        updateStatus(`Error starting agent session: ${error.message}`, 'error');
      }
    }
  }

  function connectWebSocket(tabId, sessionId) {
    if (agentWebSocket) {
      agentWebSocket.close();
    }

    const wsUrl = `ws://localhost:8008/agent/${sessionId}/ws`;
    agentWebSocket = new WebSocket(wsUrl);

    agentWebSocket.onopen = () => {
      console.log('WebSocket connected');
      updateStatus('Connected to agent session');
    };

    agentWebSocket.onmessage = async (event) => {
      try {
        const message = JSON.parse(event.data);
        console.log('WebSocket message:', message);

        if (message.type === 'apply_edit') {
          // --- apply html changes ---
          chrome.tabs.sendMessage(tabId, {
            action: 'applyAgentEdit',
            newContent: message.html,
            sessionId: sessionId
          });

          addMessageToConversation('Assistant', message.message);
          addMessageToConversation('System', 'Applied HTML changes to page');
          updateStatus(`Iteration ${message.iteration} - Applied changes, waiting for observation...`);

        } else if (message.type === 'completed') {
          addMessageToConversation('System', 'Agent session completed successfully');
          updateStatus('Agent session completed!', 'success');
          agentWebSocket.close();
          currentAgentSession = null;

        } else if (message.type === 'error') {
          addMessageToConversation('System', `Agent session failed: ${message.message}`);
          updateStatus(`Agent session failed: ${message.message}`, 'error');
          agentWebSocket.close();
          currentAgentSession = null;
        } else if (message.type === 'agent_message') {
          // Handle general agent messages
          addMessageToConversation('Assistant', message.message || message.content);
        } else if (message.type === 'status_update') {
          // Handle status updates
          addMessageToConversation('System', message.message || message.content);
          updateStatus(message.message || message.content, 'info');
        } else {
          // Handle any other message types from the agent
          if (message.message || message.content) {
            addMessageToConversation('Assistant', message.message || message.content);
          }
        }

      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };

    agentWebSocket.onclose = () => {
      console.log('WebSocket disconnected');
      updateStatus('session complete');
    };

    agentWebSocket.onerror = (error) => {
      console.error('WebSocket error:', error);
      updateStatus('WebSocket connection error', 'error');
    };
  }

  // --- send observation via websocket ---
  window.sendObservation = function (observationData) {
    if (agentWebSocket && agentWebSocket.readyState === WebSocket.OPEN) {
      agentWebSocket.send(JSON.stringify({
        type: 'observation',
        data: observationData
      }));
    }
  };

  // --- listen for messages from content script ---
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'sendObservation') {
      // Forward observation from content script to WebSocket
      if (agentWebSocket && agentWebSocket.readyState === WebSocket.OPEN) {
        agentWebSocket.send(JSON.stringify({
          type: 'observation',
          data: request.data
        }));
        console.log('Forwarded observation from content script to WebSocket');
      }
    }
  });
});