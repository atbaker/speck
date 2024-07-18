const API_URL = 'http://127.0.0.1:7725/summary';

async function getEmailSummary(threadId) {
  try {
    const response = await fetch(`${API_URL}?threadId=${threadId}`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
    return data.summary;
  } catch (error) {
    console.error('Error fetching email summary:', error);
    return 'Error fetching summary';
  }
}

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

      // Fetch the summary from the FastAPI server
      getEmailSummary(threadId).then(summary => {
        summaryText.innerText = summary;
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
