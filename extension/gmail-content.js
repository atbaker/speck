console.log("Gmail content script loaded");

async function fetchMessage(threadId) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ action: 'get_message_details', threadId: threadId }, (response) => {
      if (chrome.runtime.lastError) {
        reject(chrome.runtime.lastError);
      } else {
        resolve(response);
      }
    });
  });
};

function insertSpeckDiv() {
  const emailContainer = document.querySelector('div[role="main"]');
  if (emailContainer) {
    const subjectElement = emailContainer.querySelector('h2');
    const threadId = subjectElement.getAttribute('data-legacy-thread-id');
    if (threadId) {
      // Check if the Speck div already exists
      if (document.getElementById('speck-div')) return;

      // Create the Speck div
      const speckDiv = document.createElement('div');
      speckDiv.id = 'speck-div';

      // Create the Speck title
      const speckTitle = document.createElement('strong');
      speckTitle.innerText = 'Speck';
      speckTitle.className = 'speck-title';

      // Create the summary
      const summaryText = document.createElement('div');
      summaryText.id = 'speck-summary';

      // Create the 'start recording' button
      const startRecordingButton = document.createElement('button');
      startRecordingButton.id = 'start-recording';
      startRecordingButton.innerText = 'Start Recording';
      startRecordingButton.addEventListener("click", () => {
        console.log("Start recording button clicked");
        chrome.runtime.sendMessage({ action: "start_recording", threadId: threadId });
      });

      // Append the title and summary to the Speck div
      speckDiv.appendChild(speckTitle);
      speckDiv.appendChild(summaryText);
      speckDiv.appendChild(startRecordingButton);

      // Insert the Speck div into the Gmail UI
      subjectElement.parentElement.parentElement.parentElement.insertAdjacentElement('beforebegin', speckDiv);

      // Fetch the summary from the FastAPI server
      fetchMessage(threadId).then(messageDetails => {
        summaryText.innerText = messageDetails.summary;
      }).catch(error => {
        console.error('Error fetching message details:', error);
      });
    }
  }
}

function onThreadLoad() {
  const threadId = document.querySelector('div[role="main"] h2[data-legacy-thread-id]');
  if (threadId) {
    insertSpeckDiv();
  }
}

// Listen for changes to the URL to detect when an email is opened
let lastUrl = location.href;
new MutationObserver(() => {
  const url = location.href;
  if (url !== lastUrl) {
    lastUrl = url;
    onThreadLoad();
  }
}).observe(document, { subtree: true, childList: true });