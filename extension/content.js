console.log("Content script loaded");

let recording = false;
let threadId = null;

// Function to start recording
function startRecording(id) {
  recording = true;
  threadId = id;
  console.log("Recording started for thread ID:", threadId);

  // Create the popover div
  const popover = document.createElement('div');
  popover.id = 'recording-popover';
  popover.style.position = 'fixed';
  popover.style.top = '10px';
  popover.style.right = '10px';
  popover.style.padding = '10px';
  popover.style.backgroundColor = 'white';
  popover.style.border = '1px solid #ccc';
  popover.style.zIndex = '10000';
  popover.style.boxShadow = '0 4px 6px rgba(0, 0, 0, 0.1)';

  // Add email message ID
  const messageId = document.createElement('p');
  messageId.innerText = 'Email ID: ' + threadId;
  popover.appendChild(messageId);

  // Create the 'stop recording' button
  const stopRecordingButton = document.createElement('button');
  stopRecordingButton.innerText = 'Stop Recording';
  stopRecordingButton.addEventListener('click', () => {
    stopRecording();
  });
  popover.appendChild(stopRecordingButton);

  // Append the popover to the body
  document.body.appendChild(popover);

  // Add event listeners to record user actions
  document.addEventListener("click", recordClick);
  document.addEventListener("input", recordInput);

  // Log the initial state
  logStateChange();
}

// Function to stop recording
function stopRecording() {
  recording = false;
  console.log("Recording stopped.");

  // Remove event listeners
  document.removeEventListener("click", recordClick);
  document.removeEventListener("input", recordInput);

  // Remove the popover
  const popover = document.getElementById('recording-popover');
  if (popover) {
    document.body.removeChild(popover);
  }

  // Send the stop recording message to the background script
  chrome.runtime.sendMessage({ action: "stop_recording" });
}

// Function to record click events
function recordClick(event) {
  if (recording) {
    const entry = {
      type: "input",
      timestamp: Date.now(),
      x: event.clientX,
      y: event.clientY,
      target: event.target.outerHTML
    };
    chrome.runtime.sendMessage({ action: "log_action", entry: entry });
  }
}

// Function to record input events
function recordInput(event) {
  if (recording) {
    const entry = {
      type: "input",
      timestamp: Date.now(),
      target: event.target.outerHTML,
      value: event.target.value
    };
    chrome.runtime.sendMessage({ action: "log_action", entry: entry });
  }
}

// Function to log state changes (e.g., URL changes)
function logStateChange() {
  if (recording) {
    const entry = {
      type: "state",
      timestamp: Date.now(),
      url: window.location.href
    };
    chrome.runtime.sendMessage({ action: "log_action", entry: entry });
  }
}

// Listen for messages from the background script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("Message received in content script:", message);
  if (message.action === "start_recording") {
    startRecording(message.threadId);
    sendResponse({ status: "recording_started" }); // Send a response back to the background script
  }
});

// Check if recording is in progress when the content script loads
chrome.runtime.sendMessage({ action: "get_recording_state" }, (response) => {
  if (response && response.recording) {
    startRecording(response.threadId);
  }
});

// Listen for navigation events to log URL changes
window.addEventListener('popstate', logStateChange);
window.addEventListener('pushstate', logStateChange);
window.addEventListener('replacestate', logStateChange);
window.addEventListener('hashchange', logStateChange);
