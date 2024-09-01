let mailbox_messages = {};
let socket = null;
let currentThreadId = null;
let sidePanelPort = null;

chrome.runtime.onInstalled.addListener(() => {
  console.log('Extension installed');
  connectWebSocket();
});

chrome.runtime.onStartup.addListener(() => {
  console.log('Extension started');
  connectWebSocket();
});

function connectWebSocket() {
  socket = new WebSocket('ws://127.0.0.1:17725/ws');
  
  socket.onopen = () => {
    console.log('WebSocket connection opened');
  };

  socket.onmessage = (event) => {
    console.log('WebSocket message received:', event);
    const data = JSON.parse(event.data);
    if (data.type === 'mailbox') {
      mailbox_messages = data.messages;
      console.log('Mailbox synchronized:', mailbox_messages);
      // Broadcast the updated mailbox messages to the side panel if it's open
      if (sidePanelPort) {
        sidePanelPort.postMessage({ action: 'update_mailbox', mailbox: mailbox_messages });
      }
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
  } else if (message.action === 'execute_function') {
    const payload = {
      action: 'execute_function',
      args: message.args
    };
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(payload));
    } else {
      console.error('WebSocket is not open');
    }
  } else if (message.action === 'set_thread_id') {
    currentThreadId = message.threadId;
    // Broadcast the new thread ID to the side panel if it's open
    if (sidePanelPort) {
      sidePanelPort.postMessage({ action: 'update_thread_id', threadId: currentThreadId });
    }
  }

  return true; // Required to indicate that the response will be sent asynchronously
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url.includes('mail.google.com')) {
    chrome.sidePanel.setOptions({
      tabId,
      path: 'src/sidepanel.html',
      enabled: true
    });
  }
});

chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ tabId: tab.id });
});

chrome.runtime.onConnect.addListener((port) => {
  console.log('Connection established:', port);
  if (port.name === 'sidepanel') {
    sidePanelPort = port;
    // Send the current mailbox state when the side panel connects
    console.log('Sending mailbox to side panel:', mailbox_messages);
    sidePanelPort.postMessage({ action: 'update_mailbox', mailbox: mailbox_messages });

    port.onMessage.addListener((msg) => {
      console.log('Message received in background script:', msg);
      if (msg.action === 'get_thread_id') {
        port.postMessage({ threadId: currentThreadId });
      }
    });

    port.onDisconnect.addListener(() => {
      console.log('Side panel disconnected');
      sidePanelPort = null;
    });
  }
});