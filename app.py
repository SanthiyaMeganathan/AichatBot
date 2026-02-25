from flask import Flask, render_template, request, jsonify
from datetime import datetime, timezone,timedelta
from flask_sqlalchemy import SQLAlchemy
from google import genai
from google.genai import types
from google.api_core.exceptions import ResourceExhausted,TooManyRequests,GoogleAPIError
from sqlalchemy import CheckConstraint
import json

app = Flask(__name__)

#creating th db:
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat_history.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

#creating the database model :
class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    role = db.Column(db.String(10), nullable=False) # the role can be "user or bot"
    content = db.Column(db.Text, nullable=False) # the content of the messages between the user and bot
    timestamp =  db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc)) # the timestamp of the message

class Appointment(db.Model):
    id =db.Column(db.Integer,primary_key=True, autoincrement=True)
    name =db.Column(db.String(100),nullable=False)
    phone_number =db.Column(db.String(15), nullable=False)
    appointment_date = db.Column(db.DateTime, nullable=False)
    appointment_time = db.Column(db.Time, nullable=False)    

with app.app_context():
    db.create_all()    

client = genai.Client(api_key="AIzaSyDwDgNi9_ucNACBEDVuWIOJV1vgyWQyexc")

now_time = datetime.now(timezone.utc)
today_date = now_time.date()
weekday_name = today_date.strftime("%A")
end_date = today_date + timedelta(days=7)

SYSTEM_PROMPT = """
1. ROLE & TONE
You are a human-like, polite assistant for Dr. Akansha (Diabetes Specialist). 
also have friendly and empathetic tone.
Speak naturally, calmly, and kindly. Never be robotic.

2. GREETING RULE
- Greet the user ONLY in the first message of a new conversation.
- Ask: "How can I help you with your health concerns today?"
- If history exists, do not greet again; continue the conversation naturally.

3. CONVERSATION FLOW & INTENT
Step 1: Identify if the concern is related to Diabetes.
Step 2 (Non-Diabetes): Politely explain the clinic treats only diabetes.
Redirect to the correct specialist (e.g., Cardiologist for heart, Dermatologist for skin).
Offer future help for diabetes and end naturally.
Step 3 (Diabetes): Ask: "Would you like to book an appointment with Dr. Akansha to discuss this further?"

4. APPOINTMENT BOOKING LOGIC (NO-TOOL MODE)
If the user says YES, collect all  these details at once (or extract them if provided):
- Full Name
- Phone Number
system_prompt = f"Today's date is {today_date} ({weekday_name}). Do not book appointments on Sundays. And only book appointments for future dates. Clinic hours are 9 AM - 5 PM, 
Monday to Saturday. Always validate the following details:"
date_range_str = f"from today ({weekday_name}, {today_date}) until {end_date}"
If the user provides a date, ensure it falls within this range. If not, ask: "Please provide a valid date between {date_range_str}."
- Preferred Date (must be a valid date in the future)
- Preferred Time (must be a valid time during clinic hours: 9 AM - 5 PM, Monday to Saturday)
(phone number must be exactly 10 digits
if it does not match, ask: "Please provide a valid 10-digit phone number.")
if the phone number is corrected, prioritize the new value in all future references)
if the phone number is 12 digits and starts with +91, extract the last 10 digits and use that as the phone number.
VALIDATION RULES:
- If a phone number is not exactly 10 digits, DO NOT accept it. Ask for a correction.
- If the user provides a new value for something already discussed (like a corrected phone number), always prioritize the most recent information.

6. CLOSING & CONFIRMATION
Once all details (Name, Phone, Preferred Date, Preferred Time) are collected, provide this exact confirmation:
"Thank you, [Name]. Your appointment request for [Preferred Date] at [Preferred Time] has been booked .


8. SAFETY & BEHAVIOR
- Word Limit: Keep responses under 75 words.
- No Medical Advice: Never diagnose or prescribe. Always refer to Dr. Akansha.
- Short Replies: Treat replies like "ok", "thanks", or "hm" as a natural end to the conversation.
- Irrelevant Input: If the user talks about unrelated topics, say: "I’m sorry, I can only assist with diabetes-related concerns and appointments for Dr. Akansha."

"""


@app.route('/')
def hello_world():
    return render_template('index.html')

@app.route('/chat' , methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get('message', '')

    #save the user message to the database:
    new_user_message = ChatHistory(role='user', content =user_message, timestamp=datetime.now(timezone.utc))
    db.session.add(new_user_message)
    db.session.commit()

    past_messages= ChatHistory.query.order_by(ChatHistory.id.desc()).limit(20).all()
    past_messages.reverse()


    history_context = []
    for  message in past_messages:
         role = "user" if message.role == "user" else "model"
         history_context.append(types.Content(role=role, parts=[types.Part.from_text(text=message.content)])
             )
 
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=history_context,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT
           )
        )    
        bot_reply =response.text

        new_bot_message =ChatHistory(role='bot',content=bot_reply, timestamp=datetime.now(timezone.utc))
        db.session.add(new_bot_message)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        bot_reply=f"An error occurred while processing your request and both user message and bot message in not stored to database: {str(e)}"    

    except(ResourceExhausted, TooManyRequests) :
        bot_reply = "Rate limit exceeded. Please wait before trying again."
    except GoogleAPIError as e:
        bot_reply = f"An error occurred: {str(e)}"
    except Exception as e:
        bot_reply = f"An unexpected error occurred: {str(e)}"        

    return jsonify({'response': bot_reply})

import json # Add this import at the top
   
if __name__ == '__main__':
    app.run(debug=True)