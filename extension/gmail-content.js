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

      // Append the title and summary to the Speck div
      speckDiv.appendChild(speckTitle);
      speckDiv.appendChild(summaryText);

      // Insert the Speck div into the Gmail UI
      subjectElement.parentElement.parentElement.parentElement.insertAdjacentElement('beforebegin', speckDiv);

      // Fetch the summary from the background process
      fetchMessage(threadId).then(messageDetails => {
        summaryText.innerText = messageDetails.summary;

        // Add buttons for each selected function
        if (messageDetails.selected_functions) {
          Object.values(messageDetails.selected_functions).forEach(func => {
            const funcObj = JSON.parse(func);
            const button = document.createElement('button');
            button.innerText = `✨ ${funcObj.button_text}`;
            button.className = 'speck-function-button';
            button.setAttribute('data-message-id', threadId);
            button.setAttribute('data-function-name', funcObj.name);
            speckDiv.appendChild(button);
          });
        }

        // Add executed functions history
        if (messageDetails.executed_functions) {
          const historyTitle = document.createElement('strong');
          historyTitle.innerText = 'Function history:';
          speckDiv.appendChild(historyTitle);

          const historyList = document.createElement('ul');
          Object.values(messageDetails.executed_functions).forEach(func => {
            const funcObj = JSON.parse(func);
            const listItem = document.createElement('li');
            listItem.innerText = `${funcObj.name} - ${funcObj.status}: ${funcObj.status === 'success' ? funcObj.result.success_message : funcObj.result.error_message}`;
            historyList.appendChild(listItem);
          });
          speckDiv.appendChild(historyList);
        }
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

document.addEventListener('click', function(event) {
  if (event.target.classList.contains('speck-function-button')) {
    const button = event.target;
    const messageId = button.getAttribute('data-message-id');
    const functionName = button.getAttribute('data-function-name');

    chrome.runtime.sendMessage({
      action: 'execute_function',
      args: {
        message_id: messageId,
        function_name: functionName
      }
    });
  }
});