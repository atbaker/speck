console.log("Gmail content script loaded");

function sendThreadIdToBackground() {
    const subjectElement = document.querySelector('div[role="main"] h2[data-legacy-thread-id]');
    if (subjectElement) {
        const threadId = subjectElement.getAttribute('data-legacy-thread-id');
        if (threadId) {
          console.log('Sending threadId to background:', threadId);
          chrome.runtime.sendMessage({ action: 'set_thread_id', threadId: threadId });
        }
    }
}

// Listen for changes to the URL to detect when an email is opened
let lastUrl = location.href;
new MutationObserver(() => {
    const url = location.href;
    if (url !== lastUrl) {
        lastUrl = url;
        sendThreadIdToBackground();
    }
}).observe(document, { subtree: true, childList: true });

sendThreadIdToBackground();
