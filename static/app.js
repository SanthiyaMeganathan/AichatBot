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

        const data = await response.json();
        
        addMessageToDisplay(data.response, 'bot-message'); 
        
    } catch (error) {
        console.error('Error:', error);
        addMessageToDisplay('Sorry, something went wrong.', 'bot-message');
    }
}

function addMessageToDisplay(message, className) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', className);
    messageDiv.textContent = message;
    chatDisplay.appendChild(messageDiv);
    chatDisplay.scrollTop = chatDisplay.scrollHeight;
}

sendButton.addEventListener('click', sendMessage);

userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});
