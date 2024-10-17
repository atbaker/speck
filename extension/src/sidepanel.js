document.addEventListener('alpine:init', () => {
    Alpine.data('threadData', () => ({
        threadId: 'Loading...',
        summary: 'Fetching summary...',
        category: 'Unknown',
        mailbox: {},
        socket: null,
        messages: [], // Array to store chat messages
        userInput: '', // Input field model
        isTyping: false, // Indicates if AI is typing
        inputPlaceholder: 'Type your message', // Placeholder text
        init() {
            // Initialize WebSocket connection
            this.connectWebSocket();

            // Listen for messages from gmail-content.js
            chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
                if (message.action === 'set_thread_id') {
                    this.setThreadId(message.threadId);
                }
            });

            // Watch for changes to isTyping and update inputPlaceholder
            this.$watch('isTyping', (value) => {
                this.inputPlaceholder = value ? 'Speck is typing...' : 'Type your message';
            });
        },
        connectWebSocket() {
            this.socket = new WebSocket('ws://localhost:17725/ws');

            this.socket.onopen = (event) => {
                console.log('WebSocket connection opened.');
            };

            this.socket.onmessage = (event) => {
                const data = JSON.parse(event.data);
                console.log('Received data:', data);

                if (data.type === 'mailbox') {
                    // Update the mailbox state with data from the server
                    this.mailbox = data.payload;
                } else if (data.type === 'chat_message') {
                    // Handle incoming chat message from the backend (AI response)
                    this.addMessage('Speck', data.payload);
                    // Re-enable input
                    this.isTyping = false;
                } else if (data.type === 'error') {
                    console.error('Error from server:', data.message);
                }
            };

            this.socket.onerror = (error) => {
                console.error('WebSocket error:', error);
            };

            this.socket.onclose = (event) => {
                console.log('WebSocket connection closed.');
                // Attempt to reconnect
                setTimeout(() => {
                    this.connectWebSocket();
                }, 1000);
            };
        },
        setThreadId(newThreadId) {
            console.log('Setting thread ID to:', newThreadId);
            this.threadId = newThreadId;

            const updateThreadDetails = () => {
                if (this.mailbox.threads && this.mailbox.threads[newThreadId]) {
                    const threadDetails = this.mailbox.threads[newThreadId];
                    this.summary = threadDetails.summary || 'No summary available.';
                    this.category = threadDetails.category || 'Unknown';
                } else {
                    this.summary = 'No summary available.';
                    this.category = 'Unknown';
                }
            };

            if (this.mailbox && this.mailbox.threads) {
                updateThreadDetails();
            } else {
                // Wait for mailbox data to be loaded
                const interval = setInterval(() => {
                    if (this.mailbox && this.mailbox.threads) {
                        clearInterval(interval);
                        updateThreadDetails();
                    }
                }, 500);
            }
        },
        sendMessage() {
            if (this.userInput.trim() === '') {
                return;
            }
            const messageContent = this.userInput.trim();

            // Send message over the WebSocket
            console.log('Sending chat message:', messageContent);
            const message = {
                type: 'chat_message',
                payload: messageContent
            };
            this.socket.send(JSON.stringify(message));

            // Add user's message to the message history
            this.addMessage('User', messageContent);

            // Clear input field
            this.userInput = '';

            // Indicate that AI is typing
            this.isTyping = true;
        },
        addMessage(sender, content) {
            const messageClass = sender === 'User' ? 'flex justify-end' : 'flex';

            // Include all required classes in the bubbleClass string
            const bubbleClass = sender === 'User'
                ? 'bg-blue-500 text-white m-2 p-3 rounded-lg prose max-w-none'
                : 'bg-gray-200 m-2 p-3 rounded-lg prose max-w-none';

            // Add the message with the full class string
            this.messages.push({
                sender: sender,
                content: content,
                messageClass: messageClass,
                bubbleClass: bubbleClass
            });

            // Scroll to the bottom of the chat history
            this.$nextTick(() => {
                const chatContainer = this.$refs.chatContainer;
                chatContainer.scrollTop = chatContainer.scrollHeight;
            });
        },
        handleInput(event) {
            this.userInput = event.target.value;
        }
    }));
});
