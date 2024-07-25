let mailbox_messages = {};
let socket = null;

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
    console.log('WebSocket message received:', event);
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
  }

  return true; // Required to indicate that the response will be sent asynchronously
});