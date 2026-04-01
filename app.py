import chromadb
from flask import Flask, render_template, request, jsonify, stream_with_context, Response
from datetime import datetime, timezone, timedelta, time
from flask_sqlalchemy import SQLAlchemy
import json
import dateparser
from flask import current_app
from litellm import completion
from chromadb.utils import embedding_functions
import os
import re

app = Flask(__name__)

# If Docker sets 'OLLAMA_URL', it uses that. Otherwise, it defaults to localhost.
OLLAMA_BASE_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')


app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat_history.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    role = db.Column(db.String(10), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(15), nullable=False)
    appointment_date = db.Column(db.Date, nullable=False)
    appointment_time = db.Column(db.Time, nullable=False)

with app.app_context():
    db.create_all()

def show_available_slots(target_date_str):
    """ Tool to check available slots for the specific date. """
    parsed_date = dateparser.parse(target_date_str)
    if not parsed_date:
        return json.dumps({"status": "error", "message": "Invalid date format."})
    
    target_date = parsed_date.date()
    now = datetime.now()
    today_date = now.date()
    current_time = now.time()
    end_date = today_date + timedelta(days=7)

    if target_date < today_date:
        return json.dumps({"status": "error", "message": "Cannot book a past date."})
    if target_date > end_date:
        return json.dumps({"status": "error", "message": f"Can only book until {end_date}."})
    if target_date.strftime("%A") == "Sunday":
        return json.dumps({"status": "error", "message": "Closed on Sundays."})

    master_slots = [
        time(9, 0), time(10, 0), time(11, 0), time(12, 0),
        time(14, 0), time(15, 0), time(16, 0), time(17, 0)
    ]

    with app.app_context():
        slots_booked = Appointment.query.filter_by(appointment_date=target_date).all()
        booked_times = [appt.appointment_time for appt in slots_booked]

    valid_available_slots = []
    all_slot_statuses = []

    for slot in master_slots:
        is_booked = slot in booked_times
        has_passed = (target_date == today_date and slot <= current_time)

        if is_booked:
            status = "Booked"
        elif has_passed:
            status = "Passed"
        else:
            status = "Available"
            valid_available_slots.append(slot.strftime("%I:%M %p"))    
            
        all_slot_statuses.append(f"{slot.strftime('%I:%M %p')} is {status}")
        
    return json.dumps({
        "type": "slot",
        "status": "success",
        "target_date": str(target_date),
        "has_available_slots": len(valid_available_slots) > 0,
        "available_slots": valid_available_slots,
        "all_slot_statuses": all_slot_statuses
    })  

def book_appointment(name, phone, date_str, time_str):
    """Tool to book an appointment for the user."""
    parsed_date = dateparser.parse(date_str)
    parsed_time = dateparser.parse(time_str)

    if not parsed_date or not parsed_time:
        return json.dumps({"status": "error", "message": "Invalid date or time format."})

    target_date = parsed_date.date()
    target_time = parsed_time.time()
    now = datetime.now()
    today_date = now.date()
    current_time = now.time()
    end_date = today_date + timedelta(days=7)

 
    if target_date < today_date:
        return json.dumps({"status": "error", "message": "Cannot book a past date."})
    if target_date > end_date:
        return json.dumps({"status": "error", "message": f"Can only book until {end_date}."})
    if target_date.strftime("%A") == "Sunday":
        return json.dumps({"status": "error", "message": "Closed on Sundays."})

    master_slots = [
        time(9,0) , time(10,0) , time(11,0), time(12,0),
        time(14,0) , time(15,0) , time(16,0), time(17,0)
    ]

    if target_time not in master_slots:
        return json.dumps({"status": "error" , "message": "Invalid time. Clinic operates 9 AM to 5 PM and 1 PM to 2 PM is lunch break."})
    if target_date == today_date and target_time <= current_time:
        return json.dumps({"status":"error" , "message": "That time has already passed today."})    

    with app.app_context():
        existing_appointment = Appointment.query.filter_by(
            appointment_date=target_date, 
            appointment_time=target_time  
        ).first() 

        if existing_appointment:
            return json.dumps({"status": "error", "message": "This exact time slot is already booked."}) # Fixed missing parenthesis

      
        new_booking = Appointment(
            name=name,
            phone_number=phone,
            appointment_date=target_date,
            appointment_time=target_time
        )
        db.session.add(new_booking)
        db.session.commit()

    return json.dumps({
        "status": "success",
        "message": "Appointment confirmed",
        "details": {
            "name": name,
            "phone_number": phone,
            "appointment_date": str(target_date),
            "appointment_time": target_time.strftime("%I:%M %p")
        }
    })    

              
def fetch_appointments(user_name, user_phone_number):
    """Fetches all appointments for a given user using the username and phone number."""
    with app.app_context():

        appointments = Appointment.query.filter(
            Appointment.name.ilike(user_name),
            Appointment.phone_number == user_phone_number
        ).all()
        

        if not appointments:
            return json.dumps({
                "status":"error",
                "message":f"No appointments found for {user_name} with phone number {user_phone_number}." # Fixed typo
            })

        results = []
        for appt in appointments:
            results.append({ 
                "name": appt.name,
                "phone": appt.phone_number,
                "date": appt.appointment_date.strftime("%Y-%m-%d"),
                "time": appt.appointment_time.strftime("%I:%M %p")
            })   

        return json.dumps({
            "status": "success",
            "message": f"Found {len(results)} appointment(s).", 
            "appointments": results
        })     
    

def reschedule_appointment(name, phone, new_date_str, new_time_str):
    """Tool to reschedule an existing appointment to a new date and time."""
    parsed_new_date = dateparser.parse(new_date_str)
    parsed_new_time = dateparser.parse(new_time_str)

    if not parsed_new_date or not parsed_new_time:
        return json.dumps({
            "status":"error",
            "message":"Invalid date or time format provided." 
        })
        
    new_date_only = parsed_new_date.date()
    new_time_only = parsed_new_time.time()

    now = datetime.now()
    today_date = now.date()
    current_time = now.time()
    end_date = today_date + timedelta(days=7)

    if new_date_only < today_date:
        return json.dumps({"status": "error", "message": "Cannot reschedule to a past date."})
    if new_date_only > end_date:
        return json.dumps({"status": "error", "message": f"Can only reschedule within 7 days (until {end_date})."})
    if new_date_only.strftime("%A") == "Sunday":
        return json.dumps({"status": "error", "message": "Clinic is closed on Sundays."})

    master_slots = [
        time(9, 0), time(10, 0), time(11, 0), time(12, 0),
        time(14, 0), time(15, 0), time(16, 0), time(17, 0)
    ]    

    if new_time_only not in master_slots:
        return json.dumps({"status": "error", "message": "Invalid time. Clinic operates 9 AM to 5 PM."})
        
    if new_date_only == today_date and new_time_only <= current_time:
        return json.dumps({"status": "error", "message": "That time slot has already passed today."})

    with app.app_context():
        record = Appointment.query.filter(
            Appointment.name.ilike(name),
            Appointment.phone_number == phone
        ).first()
       

        if not record:
            return json.dumps({
                "status":"error",
                "message":f"No appointment found for {name} with phone number {phone}."
            })   

        appt_datetime = datetime.combine(record.appointment_date, record.appointment_time)
        time_diff = appt_datetime -datetime.now()

        if time_diff.total_seconds() <14400:
            return json.dumps({
                "status":"error",
                "message":"you cannot cancel or reschedule an appointment within 4 hours of the scheduled time as per clinic policy."
            })

        conflict = Appointment.query.filter_by(
            appointment_date = new_date_only,
            appointment_time = new_time_only
        ).first()   

        if conflict and conflict.id != record.id:
            return json.dumps({
                "status":"error",
                "message":"The requested time slot is already booked by another user"
            })
            
        old_date = record.appointment_date.strftime("%Y-%m-%d")
        old_time = record.appointment_time.strftime("%I:%M %p")  
        
        record.appointment_date = new_date_only
        record.appointment_time = new_time_only
        db.session.commit()

        return json.dumps({
            "status":"success",
            "message": "Appointment successfully rescheduled.",
            "details":{
                "name": name,
                "phone": phone,
                "previous_date": old_date,
                "previous_time": old_time,
                "new_date": str(new_date_only),
                "new_time": new_time_only.strftime("%I:%M %p")
            }
        })
      

def delete_appointment(name, phone):
    """ Tool to cancel or delete the existing appointment . """
    with app.app_context():
        record = Appointment.query.filter(
            Appointment.name.ilike(name),
            Appointment.phone_number == phone
        ).first()

        if not record:
            return json.dumps({ 
                "status": "error",
                "message": f"No appointment found for {name} with the phone number {phone}"
            })
        
        appt_datetime = datetime.combine(record.appointmenr_date,record.appointment_time)
        time_diff = appt_datetime - datetime.now()

        if time_diff.total_seconds()<14400:
            return json.dumps({
                "status":"error",
                "message":"you cannot cancel or reschedule an appointment now as per clinic policy, cancellations or rescheduling must be done at least 4 hours before the scheduled appointment time."
            })

        deleted_date = record.appointment_date.strftime("%Y-%m-%d")
        deleted_time = record.appointment_time.strftime("%I:%M %p")

        db.session.delete(record)
        db.session.commit()

        return json.dumps({
            "status": "success",
            "message": "Appointment successfully cancelled",
            "details": {
                "name": name,
                "phone": phone,
                "cancelled_date": deleted_date,
                "cancelled_time": deleted_time
            }
        })
def search_knowledge_base(user_query):
    """ Search the vector database and return result as a Json String""" 
    try:
        client = chromadb.PersistentClient(path="./chromadb")

        ollama_ef = embedding_functions.OllamaEmbeddingFunction(
            model_name="nomic-embed-text",
            url=f"{OLLAMA_BASE_URL}/api/embeddings",
        )
        
        collection = client.get_collection(
            name="dr_akansha_booking_system_knowledge_base",
        )
        question_embedding = ollama_ef(user_query)

        results = collection.query(
            query_embeddings=[question_embedding],
            n_results=2
        )

        documents = results.get('documents', [[]])[0]

        if not documents:
            return json.dumps({
                "status": "no_results",
                "message": "No specific information found in the knowledge base.",
                "context": ""
            })
            
        return json.dumps({
            "status": "success",
            "query": user_query,
            "context": "\n".join(documents)
        })
        
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": str(e)
        })

TOOLS = [
    {
        "type":"function",
        "function":{
            "name":"show_available_slots",
            "description":"Check available slots for a specific date.",
            "parameters":{
                "type":"object",
                "properties":{
                    "target_date_str":{"type":"string", "description": "The date to check , formatted as YYYY-MM-DD."}
                },
                "required":["target_date_str"]
            }
        }
    },
    {
        "type":"function",
        "function":{
            "name":"book_appointment",
            "description":"Book a new appointment, use this only after the user has selected the an available time",
            "parameters":{
                "type":"object",
                "properties":{
                    "name":{"type":"string", "description":"patients full name."},
                    "phone":{"type":"string", "description":"Patient's 10 digit phone number. "},
                    "date_str":{"type":"string", "description": "YYYY-MM-DD"},
                    "time_str":{"type":"string", "description":"HH:MM AM/PM"}
                },
                "required":["name","phone","date_str","time_str"]
            }
        }
    },
    {
        "type":"function",
        "function":{
            "name":"fetch_appointments",
            "description":"Look up existing appointments for a specific user",
            "parameters":{
                "type":"object",
                "properties":{
                    "user_name":{"type":"string"},
                    "user_phone_number":{"type":"string"}
                },
                "required":["user_name","user_phone_number"]
            }
        }
    },
    {
        "type":"function",
        "function":{
            "name":"reschedule_appointment",
            "description":"Move an existing appointment to new date and time",
            "parameters":{
                "type":"object",
                "properties":{
                    "name":{"type":"string"},
                    "phone":{"type":"string"},
                    "new_date_str":{"type":"string", "description":"YYYY-MM-DD"},
                    "new_time_str":{"type":"string", "description":"HH:MM AM/PM"}
                },
                "required":["name","phone","new_date_str","new_time_str"]
            }
        }
    },
    {
        "type":"function",
        "function":{
            "name":"delete_appointment",
            "description":"Cancel/delete an existing appointment",
            "parameters":{
                "type":"object",
                "properties":{
                    "name":{"type":"string"},
                    "phone":{"type":"string"}
                },
                "required":["name","phone"]
            }
        }
    },
    {
        "type":"function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Consult this for diabetes medical facts, clinic fees, fasting rules, and all clinic policies (like the 4-hour cancellation rule).",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_query": {"type": "string", "description": "The patient's question."}
                },
                "required": ["user_query"]
            }
        }
        
    }
]
@app.route('/')
def hello_world():
    return render_template('index.html')

@app.route('/clear', methods=['POST'])
def clear_history():
    try:
        db.session.query(ChatHistory).delete()
        db.session.commit()
        return jsonify({"status":"success","message":"Chat history table cleared."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status":"error","message":f"Failed to clear chat history: {str(e)}"}) 

@app.route('/chat', methods=['POST'])
def chat_route():
    ist_offset = timedelta(hours=5, minutes=30)
    now_ist = datetime.now(timezone.utc) + ist_offset
    
    today_date = now_ist.date()
    weekday_name = today_date.strftime("%A")
    current_time_str = now_ist.strftime("%H:%M")  # Railway time (24-hour)
    end_date = today_date + timedelta(days=7)

    SYSTEM_PROMPT = f"""
1. ROLE & TONE
You are a polite, empathetic, and human-like assistant for Dr. Akansha (Diabetes Specialist).
Speak naturally and calmly. Keep responses under 40 words. 
Ask ONLY ONE question per response. Never reveal internal tool names or JSON.
Dont speak like engineer or programmer or dont use technical terms like error , codes or database or json or embedding or vector database etc.

If the user ask for the any information that is from the knowledge base you should use the tool `search_knowledge_base` to fetch the information and share it with user in a human readable format. If the user ask for the information that is not present in knowledge base you can say "I'm not sure about that specific detail, but Dr. Akansha can discuss it during your visit."
For answering the questions from knowledge base , you dont need to start fromgreeting or asking about health concern, you can directly answer the question by fetching the information from knowledge base using the tool `search_knowledge_base` and share it with user in a human readable format. Always use the tool `search_knowledge_base` to fetch the information from 
knowledge base and share it with user in a human readable format whenever user ask for the information related to clinic policies, 
diabetes facts, patient instructions or any other information that is present in knowledge base.

2. GREETING & SCOPE
- Greet with: "Hello, I'm Dr. Akansha's assistant. How can I help you with your health concerns today?"
- Dr. Akansha ONLY treats diabetes. For other issues, suggest a specialist and do not book.

3.KNOWLEDGE RETRIEVAL (RAG): You MUST use the search_knowledge_base tool whenever a user asks about:
Clinic Overview & Scope (Specialization, hours, treatment limits).
Appointment Policies (Fees, 4-hour rule, booking windows).
Patient Instructions (Fasting rules, required documents/logs).
Diabetes Facts & Medical FAQ (Type 1/2, Hypo/Hyperglycemia, HbA1c).
Tool Fallback: If search_knowledge_base returns "no_results", say: "I'm not sure about that specific detail, but Dr. Akansha can discuss it during your visit."
The 4-Hour Rule: For late cancellations/reschedules (<4 hours remaining), strictly state: "You cannot cancel or reschedule your appointment now because you have less than 4 hours left until your appointment."
Scope & Hours: Focus exclusively on Diabetes. Clinic hours are Mon-Sat, 9:00 AM – 5:00 PM (Closed 1:00 PM – 2:00 PM and Sundays). Fee: 500 INR


strict rule: For booking you must follow the exact flow and ask questions in the specified order. Do not deviate from the flow or ask for information that is not required at that step. Always confirm the user's choices before proceeding to the next step.
4. CONVERSATION & BOOKING FLOW
Prerequisite:After greeting , ask the user about their health concern. If it's diabetes-related, ask if they want to book an appointment.
If they say 'no', end the conversation politely. If they say 'yes', follow the steps below in order:

You dont need to say I am sorry in every response, you can be empathetic and polite without saying sorry in every response. You can say sorry only when there is a error or when user ask for the information that is not present in knowledge base.'
 Always try to be empathetic and polite without saying sorry in every response.
Step 0: If diabetes-related, ask if they want to book. 
If 'no', end politely.
 If 'yes', follow steps:
Step 1: Ask The Full Name 
Step 2: Ask for the 10-digit Phone number
Step 3: Ask for a Preferred Date 
Step 4: Ask the user if they want to see the available slots for the preferred date that they mentioned
Step 5: If the user says yes, use this `show_available_slots` tool and show the slots , when ever you show the slots to user always use this tool `show_available_slots` and show it in gen ui.
Step 6: The user will choose a slot from the available options
Step 7: Use this tool `book_appointment` to book the appointment

5. CANCELLATION & RESCHEDULING
- Use `fetch_appointments`, `reschedule_appointment`, or `delete_appointment` for changes.
- If a user asks about the cancellation policy or reschedule policy, use `search_knowledge_base` to explain the 4-hour rule.
- If a tool returns an error (like "less than 4 hours left"), explain it gently to the user.That we cannot cancel or reschedule the appointment when we have less than 4 hours left for the appointment timing.

6. STRICT LIMITS
- Do not give medical prescriptions or specific diagnoses.
- Stop generating text immediately after finishing your sentence.

CURRENT SYSTEM CONTEXT:
Today's date is {today_date} ({weekday_name})
Current time is {current_time_str}
Appointments allowed until {end_date}

MOST IMPORTANT RULE: never return anything as a json.



"""

    data = request.get_json()
    user_message = data.get('message', '')

    try:

        db.session.add(ChatHistory(role='user', content=user_message))
        db.session.commit()

       
        past_messages = ChatHistory.query.order_by(ChatHistory.id.desc()).limit(20).all()
        past_messages.reverse()

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in past_messages:
            role = "assistant" if msg.role == "bot" else "user"
            messages.append({"role": role, "content": msg.content})

        @stream_with_context 
        def generate():
            response = completion(
                model='ollama/gpt-oss:120b-cloud',
                messages=messages,
                api_base=OLLAMA_BASE_URL,
                temperature=0.4,
                tools=TOOLS,
                stream=False
            )

            response_message = response.choices[0].message
            full_bot_reply = ""
            
            if response_message.tool_calls:
                messages.append(response_message)
                short_circuit_json = None

                for tool_call in response_message.tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)

                    if func_name == "show_available_slots":
                        result = show_available_slots(args.get("target_date_str"))
                        parsed_result = json.loads(result)
                        if parsed_result.get("status") == "success":
                            short_circuit_json = result
                    elif func_name == "book_appointment":
                        result = book_appointment(args.get("name"), args.get("phone"), args.get("date_str"), args.get("time_str")) 
                    elif func_name == "fetch_appointments":
                        result = fetch_appointments(args.get("user_name"), args.get("user_phone_number"))  
                    elif func_name == "reschedule_appointment":
                        result = reschedule_appointment(args.get("name"), args.get("phone"), args.get("new_date_str"), args.get("new_time_str"))  
                    elif func_name == "delete_appointment":
                        result = delete_appointment(args.get("name"), args.get("phone"))  
                    elif func_name == "search_knowledge_base":
                        result=search_knowledge_base(args.get("user_query"))    
                    else:
                        result = json.dumps({"error": "Function not found"})    

                    messages.append({
                        "role": "tool",
                        "name": func_name,
                        "content": result,
                        "tool_call_id": tool_call.id
                    })

             
                if short_circuit_json:
                    full_bot_reply = short_circuit_json
                    yield short_circuit_json    
                else:
                    final_response = completion(
                        model='ollama/gpt-oss:120b-cloud',
                        messages=messages,
                        api_base=OLLAMA_BASE_URL,
                        temperature=0.4,
                        stream=True
                    )
                    for chunk in final_response:
                        token = chunk.choices[0].delta.content or ""
                        if token:
                            full_bot_reply += token
                            yield token
            else:
           
                full_bot_reply = response_message.content or ""
                full_bot_reply = re.sub(r'\{\s*"name".*?"arguments".*?\}', '', full_bot_reply, flags=re.DOTALL).strip()
                yield full_bot_reply

            try:
                with current_app.app_context():
                    db.session.add(ChatHistory(role='bot', content=full_bot_reply.strip())) 
                    db.session.commit()
            except Exception as e:
                print("DB ERROR", str(e))
                db.session.rollback()

        return Response(generate(), mimetype='text/plain')

    except Exception as e:
        db.session.rollback()
        return jsonify({'response': f"Error: {str(e)}"})                                  
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)