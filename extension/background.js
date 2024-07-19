let mailbox_messages = {};
let socket = null;
let currentThreadId = null;
let recording = false;
let scenarioLog = [];

chrome.runtime.onInstalled.addListener(() => {
  console.log('Extension installed');
  connectWebSocket();
});

function connectWebSocket() {
  socket = new WebSocket('ws://127.0.0.1:17725/ws');
  
  socket.onopen = () => {
    console.log('WebSocket connection opened');
  };

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'mailbox') {
      mailbox_messages = data.messages;
      console.log('Mailbox synchronized:', mailbox_messages);
    }
  };

  socket.onclose = () => {
    console.log('WebSocket connection closed. Reconnecting in 5 seconds...');
    setTimeout(connectWebSocket, 5000);
  };

  socket.onerror = (error) => {
    console.error('WebSocket error:', error);
  };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("Message received in background script:", message);
  if (message.action === 'get_message_details') {
    const messageDetails = mailbox_messages[message.threadId] || 'No message available.';
    sendResponse(messageDetails);
  } else if (message.action === 'start_recording') {
    currentThreadId = message.threadId;
    recording = true;
    scenarioLog = [];
    chrome.tabs.create({ url: 'https://www.usps.com' }, (tab) => {
      chrome.tabs.onUpdated.addListener(function listener(tabId, info) {
        if (info.status === 'complete' && tabId === tab.id) {
          chrome.tabs.onUpdated.removeListener(listener);
          console.log("Sending start recording message to content script");
          chrome.tabs.sendMessage(tab.id, { action: "start_recording", threadId: currentThreadId }, (response) => {
            if (chrome.runtime.lastError) {
              console.error("Error sending message to content script:", chrome.runtime.lastError);
            } else {
              console.log("Message sent to content script successfully", response);
            }
          });
        }
      });
    });
  } else if (message.action === 'stop_recording') {
    recording = false;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ action: 'stop_recording', scenarioLog: scenarioLog }));
    } else {
      console.error('WebSocket is not open. Cannot send message.');
    }
  } else if (message.action === 'log_action') {
    if (recording) {
      scenarioLog.push(message.entry);
    }
  } else if (message.action === 'get_recording_state') {
    sendResponse({ recording: recording, threadId: currentThreadId });
  }
  return true; // Required to indicate that the response will be sent asynchronously
});