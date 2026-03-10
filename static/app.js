const sendButton = document.getElementById('sendButton');
const userInput = document.getElementById('userInput');
const chatDisplay = document.getElementById('chatDisplay');

async function sendMessage() {
    const text = userInput.value.trim(); 
    if (text === '') return;

    addMessageToDisplay(text, 'user-message');
    userInput.value = '';

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message: text })
        });

        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', 'bot-message');
        chatDisplay.appendChild(messageDiv);
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let botReply = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break; 
            
            const chunk = decoder.decode(value, { stream: true });
            botReply += chunk;
            
            // Look how clean this is now! No more .split() needed.
            messageDiv.innerHTML = marked.parse(botReply);
            chatDisplay.scrollTop = chatDisplay.scrollHeight;
        }

        // Final parse just to be safe
        messageDiv.innerHTML = marked.parse(botReply.trim());
        
    } catch (error) {
        console.error('Error:', error);
        addMessageToDisplay('Sorry, something went wrong.', 'bot-message');
    }
}

function addMessageToDisplay(message, className) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', className);
    
    if (className === 'bot-message') {
        // No more string splitting here either!
        messageDiv.innerHTML = marked.parse(message.trim());
    } else {
        messageDiv.textContent = message;
    }

    chatDisplay.appendChild(messageDiv);
    chatDisplay.scrollTop = chatDisplay.scrollHeight;
}

sendButton.addEventListener('click', sendMessage);

userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});