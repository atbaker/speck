document.addEventListener('DOMContentLoaded', () => {
    console.log('FOOO');
    const port = chrome.runtime.connect({ name: 'sidepanel' });
    port.postMessage({ action: 'get_thread_id' });

    port.onMessage.addListener((message) => {
        console.log('Message received in sidepanel:', message);
        if (message.action === 'update_thread_id') {
            document.dispatchEvent(new CustomEvent('setThreadId', { detail: message.threadId }));
        } else if (message.action === 'update_mailbox') {
            console.log('Updating mailbox:', message.mailbox);
            document.dispatchEvent(new CustomEvent('setMailbox', { detail: message.mailbox }));
        } else if (message.action === 'update_thread_details') {
            console.log('Updating thread details:', message.threadDetails);
            document.dispatchEvent(new CustomEvent('setThreadDetails', { detail: message.threadDetails }));
        }
    });
});

document.addEventListener('alpine:init', () => {
    Alpine.data('threadData', () => ({
        threadId: 'Loading...',
        summary: 'Fetching summary...',
        category: 'Unknown',
        mailbox: {},
        selectedFunctions: [],
        init() {
            document.addEventListener('setThreadId', (event) => {
                this.setThreadId(event.detail);
            });
            document.addEventListener('setMailbox', (event) => {
                this.setMailbox(event.detail);
            });
            document.addEventListener('setThreadDetails', (event) => {
                this.setThreadDetails(event.detail);
            });
        },
        setThreadId(newThreadId) {
            console.log('Setting thread ID to:', newThreadId);
            this.threadId = `Thread ID: ${newThreadId}`;
            this.updateDetails(newThreadId);
        },
        setMailbox(newMailbox) {
            this.mailbox = newMailbox;
            this.updateDetails(this.threadId);
        },
        setThreadDetails(threadDetails) {
            this.summary = threadDetails ? threadDetails.summary : 'No summary available.';
            this.category = threadDetails ? threadDetails.category : 'Unknown';
        },
        updateDetails(threadId) {
            chrome.runtime.sendMessage({ action: 'get_thread_details', threadId: threadId }, (response) => {
                this.setThreadDetails(response);
            });
        }
    }));
});