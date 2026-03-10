from flask import Flask, render_template, request, jsonify, stream_with_context, Response
from datetime import datetime, timezone, timedelta, time
from flask_sqlalchemy import SQLAlchemy
import json
import dateparser
from flask import current_app
from litellm import completion
app = Flask(__name__)

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
        appointments = Appointment.query.filter_by(name=user_name, phone_number=user_phone_number).all()

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
        record = Appointment.query.filter_by(name=name, phone_number=phone).first()

        if not record:
            return json.dumps({
                "status":"error",
                "message":f"No appointment found for {name} with phone number {phone}."
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
        record = Appointment.query.filter_by(name=name, phone_number=phone).first()

        if not record:
            return json.dumps({ 
                "status": "error",
                "message": f"No appointment found for {name} with the phone number {phone}"
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
    }
]




@app.route('/')
def hello_world():
    return render_template('index.html')

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
Speak naturally and calmly. Never sound robotic.
Never reveal your internal tool usage, JSON, or thinking process to the user.

2. GREETING & SCOPE
- Greet new conversations with exactly: "Hello, I'm Dr. Akansha's assistant. How can I help you with your health concerns today?"
- Dr. Akansha ONLY treats diabetes. If the user mentions a non-diabetes issue, politely recommend they see an appropriate specialist (e.g., Dermatologist) and do not offer to book an appointment.

3. CONVERSATION & BOOKING FLOW
You must gather information strictly ONE piece at a time to keep it conversational. 
Do not ask for Name, Phone, and Date in the same sentence. 
Follow this order for bookings:
  Step 1: Ask for Full Name.
  Step 2: Ask for 10-digit Phone Number.
  Step 3: Ask for Preferred Date.
  Step 4: Use the `show_available_slots` tool to check that date.
  Step 5: Present ONLY the available slots to the user and ask them to pick one.
  Step 6: Use the `book_appointment` tool to finalize the booking.

4. TOOL USAGE & ERROR HANDLING
- NEVER invent, guess, or assume available time slots. You MUST use the `show_available_slots` tool.
- If a tool returns a JSON with "status": "error" (e.g., the date is in the past, or the clinic is closed), gently explain the exact error to the user and ask them to provide a new date or time.
- Use `fetch_appointments`, `reschedule_appointment`, or `delete_appointment` when the user asks to view, change, or cancel their bookings.

5. STRICT OUTPUT CONTROL
- Keep your responses under 40 words.
- Ask ONLY ONE question per response.
- NEVER answer your own questions or simulate the user's reply.
- Stop generating text the absolute second you finish your sentence.

CURRENT SYSTEM CONTEXT:
Today's date is {today_date} ({weekday_name})
Current time is {current_time_str}
Appointments allowed from today until {end_date}
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
                api_base="http://localhost:11434",
                temperature=0.4,
                tools=TOOLS,
                stream=False
            )

            response_message = response.choices[0].message
            full_bot_reply = ""
            
            if response_message.tool_calls:
                messages.append(response_message)

               
                for tool_call in response_message.tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)

                    if func_name == "show_available_slots":
                        result = show_available_slots(args.get("target_date_str"))
                    elif func_name == "book_appointment":
                        result = book_appointment(args.get("name"), args.get("phone"), args.get("date_str"), args.get("time_str")) 
                    elif func_name == "fetch_appointments":
                        result = fetch_appointments(args.get("user_name"), args.get("user_phone_number"))  
                    elif func_name == "reschedule_appointment":
                        result = reschedule_appointment(args.get("name"), args.get("phone"), args.get("new_date_str"), args.get("new_time_str"))  
                    elif func_name == "delete_appointment":
                        result = delete_appointment(args.get("name"), args.get("phone"))   
                    else:
                        result = json.dumps({"error": "Function not found"})    

                    messages.append({
                        "role": "tool",
                        "name": func_name,
                        "content": result,
                        "tool_call_id": tool_call.id
                    })

            
                final_response = completion(
                    model='ollama/gpt-oss:120b-cloud',
                    messages=messages,
                    api_base="http://localhost:11434",
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
    app.run(debug=True)