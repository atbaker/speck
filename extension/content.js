const API_URL = 'http://127.0.0.1:7725/summary';

function getEmailSummary(threadId) {
  return fetch(`${API_URL}?threadId=${threadId}`)
    .then(response => response.json())
    .then(data => data.summary)
    .catch(error => {
      console.error('Error fetching email summary:', error);
      return 'Error fetching summary';
    });
}

function addSummaryDiv(threadId) {
  const emailContainer = document.querySelector('div[role="main"]'); // Adjust the selector as needed
  if (!emailContainer) return;

  const summaryDiv = document.createElement('div');
  summaryDiv.id = 'speck-summary';
  summaryDiv.style.border = '1px solid #ccc';
  summaryDiv.style.padding = '10px';
  summaryDiv.style.marginBottom = '10px';

  getEmailSummary(threadId).then(summary => {
    summaryDiv.textContent = summary;
  });

  // Insert the summary div into the page
  const subjectElement = emailContainer.querySelector('.hP'); // Adjust the selector as needed
  if (subjectElement) {
    subjectElement.insertAdjacentElement('afterend', summaryDiv);
  }
}

function onThreadLoad() {
  const threadId = document.querySelector('div[role="main"] h2[data-legacy-thread-id]')
  if (threadId) {
    addSummaryDiv(threadId.getAttribute('data-legacy-thread-id'));
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
