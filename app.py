"""
PTAI Assistant PK — Backend
---------------------------
Built on top of the original app.py logic (Gemini chat + OpenWeatherMap tool),
with MySQL added for:
  - user accounts (signup/login/logout/session)
  - per-user chat history (saved + retrievable)

SAME API keys as your original app.py are kept below exactly as you had them.
If you rotate them later, this is the only place you need to update.
"""

from flask import Flask, render_template, request, jsonify, session
import google.generativeai as genai
import requests
import json
import os
import uuid
import datetime
import mysql.connector
from mysql.connector import pooling
from werkzeug.security import generate_password_hash, check_password_hash

# ==========================================
#  CONFIGURATION - YOUR EXISTING KEYS
# ==========================================
GEMINI_API_KEY = "AQ.Ab8RN6LUrCW7vjcgcaVkTEeFDqGHJKqyI_qs0v8hKSVu4C5xBg"
OWM_API_KEY = "af19282eda983ed5d29701d02903f16c"

# ==========================================
#  MYSQL CONFIGURATION - EDIT THESE FOR YOUR MACHINE
# ==========================================
MYSQL_CONFIG = {
    "host": os.environ.get("PTAI_DB_HOST", "localhost"),
    "user": os.environ.get("PTAI_DB_USER", "root"),
    "password": os.environ.get("PTAI_DB_PASSWORD", ""),
    "database": os.environ.get("PTAI_DB_NAME", "ptai_db"),
}

app = Flask(__name__)
app.secret_key = os.environ.get("PTAI_SECRET_KEY", "dev-secret-change-me")

# In-memory per-session Gemini chat objects (Gemini chat sessions can't be
# stored in cookies/DB, so we keep them server-side keyed by a session id).
CHAT_SESSIONS = {}

db_pool = None


# ---------------------------------------------------------------
# DATABASE SETUP
# ---------------------------------------------------------------
def init_db_pool():
    global db_pool
    db_pool = pooling.MySQLConnectionPool(pool_name="ptai_pool", pool_size=5, **MYSQL_CONFIG)


def get_db():
    return db_pool.get_connection()


def init_tables():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(80) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            full_name VARCHAR(120),
            email VARCHAR(150) UNIQUE,
            gender VARCHAR(30),
            age INT,
            country VARCHAR(80),
            created_at DATETIME NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            message TEXT NOT NULL,
            response TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    cur.close()
    conn.close()


# ---------------------------------------------------------------
# Weather Tool Helper (unchanged logic from your original app.py)
# ---------------------------------------------------------------
def fetch_weather_data(city_name):
    if OWM_API_KEY == "YOUR_OPENWEATHERMAP_API_KEY_HERE" or len(OWM_API_KEY) < 10:
        return {"error": "API Key Missing"}

    base_url = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        'q': f"{city_name},PK",  # Restrict to Pakistan
        'appid': OWM_API_KEY,
        'units': 'metric'
    }
    try:
        response = requests.get(base_url, params=params, timeout=5)
        data = response.json()
        if response.status_code == 200:
            weather_id = data['weather'][0]['id']
            icon_name = "ph-sun"
            if 200 <= weather_id <= 232: icon_name = "ph-cloud-lightning"
            elif 300 <= weather_id <= 531: icon_name = "ph-cloud-rain"
            elif 600 <= weather_id <= 622: icon_name = "ph-snowflake"
            elif 701 <= weather_id <= 781: icon_name = "ph-cloud-fog"
            elif weather_id == 800: icon_name = "ph-sun"
            elif weather_id > 800: icon_name = "ph-cloud"

            return {
                "location": data['name'],
                "temperature": round(data['main']['temp']),
                "condition": data['weather'][0]['main'],
                "description": data['weather'][0]['description'],
                "humidity": data['main']['humidity'],
                "wind": data['wind']['speed'],
                "icon": icon_name
            }
        else:
            return {"error": data.get('message', 'Unknown error')}
    except Exception as e:
        return {"error": str(e)}


def get_current_weather_in_pakistan(city_name: str):
    """Tool used by the AI to fetch weather"""
    data = fetch_weather_data(city_name)
    if "error" in data:
        return json.dumps({"error": f"Could not get weather for {city_name}."})

    ai_friendly_data = {
        "location": data['location'],
        "temperature": f"{data['temperature']}°C",
        "condition": data['description'],
        "humidity": f"{data['humidity']}%"
    }
    return json.dumps(ai_friendly_data)


SYSTEM_PROMPT = """
You are "PTAI Assistant PK", an intelligent AI guide specialized in Pakistan tourism and weather.
Your tasks:
1. Provide current weather updates for Pakistani cities using the available tool.
2. Share accurate historical, cultural, and safety information about tourist destinations in Pakistan.
Guidelines:
- Be helpful, professional, and concise.
- Keep responses structured and easy to read on a web interface.
- Always identify as PTAI Assistant PK.
"""
GEMINI_MODEL_NAME = 'gemini-2.5-flash'
model = genai.GenerativeModel(GEMINI_MODEL_NAME)
genai_ready = False


def init_genai():
    global genai_ready
    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE" or len(GEMINI_API_KEY) < 10:
        print("--- CRITICAL ERROR: Google Gemini API Key not set in app.py ---")
        return False
    genai.configure(api_key=GEMINI_API_KEY)
    genai_ready = True
    print(f"--- AI configured successfully using {GEMINI_MODEL_NAME} ---")
    return True


def get_chat_session(session_key):
    """Return an existing Gemini chat session for this browser session, or create one."""
    if session_key in CHAT_SESSIONS:
        return CHAT_SESSIONS[session_key]
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL_NAME,
        tools=[get_current_weather_in_pakistan],
        system_instruction=SYSTEM_PROMPT
    )
    chat = model.start_chat(enable_automatic_function_calling=True)
    CHAT_SESSIONS[session_key] = chat
    return chat


def get_browser_session_key():
    """Every browser gets a stable key (logged-in users use their user_id, guests get a uuid)."""
    if "user_id" in session:
        return f"user-{session['user_id']}"
    if "guest_id" not in session:
        session["guest_id"] = str(uuid.uuid4())
    return f"guest-{session['guest_id']}"


# ---------------------------------------------------------------
# AUTH ROUTES
# ---------------------------------------------------------------
@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    gender = (data.get("gender") or "").strip()
    age = data.get("age")
    country = (data.get("country") or "").strip()

    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400
    if not full_name:
        return jsonify({"error": "Please enter your full name."}), 400
    if not email or "@" not in email:
        return jsonify({"error": "Please enter a valid email address."}), 400
    if gender not in ("Male", "Female", "Other", "Prefer not to say"):
        return jsonify({"error": "Please select a gender option."}), 400

    # age is optional, but validate it if provided
    age_value = None
    if age not in (None, "",):
        try:
            age_value = int(age)
            if age_value < 13 or age_value > 120:
                return jsonify({"error": "Please enter a valid age."}), 400
        except (TypeError, ValueError):
            return jsonify({"error": "Age must be a number."}), 400

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id FROM users WHERE username = %s", (username,))
    if cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({"error": "That username is already taken."}), 400

    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    if cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({"error": "An account with that email already exists."}), 400

    password_hash = generate_password_hash(password)
    cur.execute(
        """
        INSERT INTO users (username, password_hash, full_name, email, gender, age, country, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (username, password_hash, full_name, email, gender, age_value, country, datetime.datetime.utcnow()),
    )
    conn.commit()
    user_id = cur.lastrowid
    cur.close()
    conn.close()

    session["user_id"] = user_id
    session["username"] = username
    return jsonify({"user": {"id": user_id, "username": username, "full_name": full_name}})


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password."}), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    return jsonify({"user": {"id": user["id"], "username": user["username"]}})


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/session", methods=["GET"])
def check_session():
    if "user_id" in session:
        return jsonify({"logged_in": True, "user": {"id": session["user_id"], "username": session["username"]}})
    return jsonify({"logged_in": False})


# ---------------------------------------------------------------
# CHAT + HISTORY ROUTES
# ---------------------------------------------------------------
@app.route("/chat", methods=["POST"])
def chat():
    if not genai_ready:
        return jsonify({"response": "System Error: AI offline."})

    user_message = request.json.get("message")
    if not user_message or user_message.strip() == "":
        return jsonify({"response": "Empty message."})

    session_key = get_browser_session_key()
    chat_session = get_chat_session(session_key)

    try:
        print(f"User: {user_message}")
        response = chat_session.send_message(user_message)
        bot_text = response.text
    except Exception as e:
        print(f"Generation Error: {e}")
        return jsonify({"response": "Temporary connection error. Please try again."})

    # Save to MySQL only if logged in
    if "user_id" in session:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO chat_history (user_id, message, response, created_at) VALUES (%s, %s, %s, %s)",
            (session["user_id"], user_message, bot_text, datetime.datetime.utcnow()),
        )
        conn.commit()
        cur.close()
        conn.close()

    return jsonify({"response": bot_text})


@app.route("/get_history", methods=["GET"])
def get_history():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in."}), 401

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT message, response, created_at FROM chat_history WHERE user_id = %s ORDER BY id DESC LIMIT 50",
        (session["user_id"],),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    history = [
        {
            "message": row["message"],
            "response": row["response"],
            "timestamp": row["created_at"].strftime("%Y-%m-%d %H:%M"),
        }
        for row in rows
    ]
    return jsonify({"history": history})


# ---------------------------------------------------------------
# WEATHER DASHBOARD + INDEX
# ---------------------------------------------------------------
@app.route("/get_dashboard_weather")
def get_dashboard_weather():
    cities = ["Islamabad", "Karachi", "Lahore", "Peshawar", "Quetta"]
    dashboard_data = []
    for city in cities:
        data = fetch_weather_data(city)
        if "error" not in data:
            dashboard_data.append(data)
    return jsonify(dashboard_data)


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    print("--- Starting PTAI Web Server ---")
    init_genai()
    init_db_pool()
    init_tables()
    print("Ensure VPN is ON if required.")
    app.run(debug=False, port=5000)
