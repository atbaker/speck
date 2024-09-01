document.addEventListener('DOMContentLoaded', () => {
    console.log('FOOO');
    const port = chrome.runtime.connect({ name: 'sidepanel' });
    port.postMessage({ action: 'get_thread_id' });

    port.onMessage.addListener((message) => {
        console.log('Message received in sidepanel:', message);
        if (message.action === 'update_thread_id') {
            Alpine.store('threadStore').setThreadId(message.threadId);
        } else if (message.action === 'update_mailbox') {
            console.log('Updating mailbox:', message.mailbox);
            Alpine.store('threadStore').setMailbox(message.mailbox);
        }
    });
});

document.addEventListener('alpine:init', () => {
    Alpine.store('threadStore', {
        threadId: 'Loading...',
        summary: 'Fetching summary...',
        mailbox: {},
        setThreadId(newThreadId) {
            console.log('Setting thread ID to:', newThreadId);
            this.threadId = `Thread ID: ${newThreadId}`;
            this.updateSummary(newThreadId);
        },
        setMailbox(newMailbox) {
            this.mailbox = newMailbox;
            this.updateSummary(this.threadId);
        },
        updateSummary(threadId) {
            const messageDetails = this.mailbox[threadId];
            this.summary = messageDetails ? messageDetails.summary : 'No summary available.';
        }
    });
});