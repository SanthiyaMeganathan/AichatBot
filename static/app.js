const sendButton = document.getElementById('sendButton');
const userInput = document.getElementById('userInput');
const chatDisplay = document.getElementById('chatDisplay');

window.onload = async() =>{
    try{
        await fetch('/clear',{ method: 'POST'});
        console.log("Chat history cleared on reload.");

    }catch(e){
        console.error("failed to clear history.",e);
    }
};

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
        

        let isSlotRendered = false; 

        while (true) {
            const { done, value } = await reader.read();
            if (done) break; 
            
            const chunk = decoder.decode(value, { stream: true });
            botReply += chunk;

            if(botReply.trim().startsWith('{') && botReply.includes('"type": "slot"')) {
                try {
                    const slotData = JSON.parse(botReply);
                    renderSlotButtons(slotData, messageDiv);
                    isSlotRendered = true; 
                } catch (e) {
                    console.error('Failed to parse slot data:', e);
                }
            } else if (!isSlotRendered) {
                messageDiv.innerHTML = marked.parse(botReply);
            }
            chatDisplay.scrollTop = chatDisplay.scrollHeight;
        }

        if (!isSlotRendered) {
            messageDiv.innerHTML = marked.parse(botReply.trim());
        }
        
    } catch (error) {
        console.error('Error:', error);
        addMessageToDisplay('Sorry, something went wrong.', 'bot-message');
    }
}

function renderSlotButtons(data, container) {
    if (data.status === "success" && data.available_slots.length > 0) {
        let html = `<div class="slot-container">
                        <p>Available on ${data.target_date}:</p>`;
        
        data.available_slots.forEach(slot => {
            html += `
                <div class="slot-row">
                    <span class="slot-time">${slot}</span>
                    <button class="select-btn" onclick="selectSlot('${slot}', '${data.target_date}')">
                        Select
                    </button>
                </div>`;
        });

        html += `</div>`;
        container.innerHTML = html;
    } else {
        container.innerHTML = `<p class="error-msg">${data.message || "No slots available."}</p>`;
    }
}

function selectSlot(time, date) {
    userInput.value = `I would like to book the ${time} slot on ${date}`;
    sendMessage(); 
} 

function addMessageToDisplay(message, className) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', className);
    
    if (className === 'bot-message') {
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