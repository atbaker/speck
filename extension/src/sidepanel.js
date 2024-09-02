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
        }
    });
});

document.addEventListener('alpine:init', () => {
    Alpine.data('threadData', () => ({
        threadId: 'Loading...',
        summary: 'Fetching summary...',
        messageType: 'Unknown',
        mailbox: {},
        selectedFunctions: [],
        init() {
            document.addEventListener('setThreadId', (event) => {
                this.setThreadId(event.detail);
            });
            document.addEventListener('setMailbox', (event) => {
                this.setMailbox(event.detail);
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
        updateDetails(threadId) {
            const messageDetails = this.mailbox[threadId];
            this.summary = messageDetails ? messageDetails.summary : 'No summary available.';
            this.messageType = messageDetails ? messageDetails.message_type : 'Unknown';
        }
    }));
});