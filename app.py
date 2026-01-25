from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
import nltk
import string
from nltk.tokenize import word_tokenize
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from werkzeug.security import generate_password_hash, check_password_hash

nltk.download("punkt")

app = Flask(__name__)
app.secret_key = "college_chatbot_secret"

# ---------------- DATABASE CONNECTION ----------------
def get_db():
    return sqlite3.connect("database.db")

# ---------------- CREATE TABLES ----------------
def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS intents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag TEXT UNIQUE
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            intent_id INTEGER,
            pattern TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            intent_id INTEGER,
            response TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            bot TEXT,
            time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            message TEXT,
            type TEXT,
            status TEXT DEFAULT 'Pending',
            time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS college_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            field TEXT UNIQUE,
            value TEXT
        )
    """)

    conn.commit()
    conn.close()

# ---------------- AUTO SEED DATA ----------------
def seed_data():
    conn = get_db()
    c = conn.cursor()

    # Seed Admin
    c.execute("SELECT * FROM admins WHERE username='admin'")
    if not c.fetchone():
        password_hash = generate_password_hash("chatbot@777")
        c.execute("INSERT INTO admins (username, password) VALUES (?, ?)",
                  ("admin", password_hash))

    # Seed College Info
    college_data = {
        "name": "Vijaya College, Mulki",
        "address": "Mulki, Karnataka",
        "phone": "9876543210",
        "courses": "BCA, BCom, BSc",
        "office_time": "9:30 AM to 4:30 PM"
    }

    for k, v in college_data.items():
        c.execute("INSERT OR IGNORE INTO college_info (field, value) VALUES (?, ?)", (k, v))

    # Seed Default Intent
    c.execute("SELECT COUNT(*) FROM intents")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO intents (tag) VALUES (?)", ("greeting",))
        intent_id = c.lastrowid

        patterns = ["hi", "hello", "hey", "good morning"]
        responses = [
            "Hello! How can I help you?",
            "Hi 😊 Ask me anything about the college.",
            "Welcome to the college chatbot!"
        ]

        for p in patterns:
            c.execute("INSERT INTO patterns (intent_id, pattern) VALUES (?, ?)", (intent_id, p))

        for r in responses:
            c.execute("INSERT INTO responses (intent_id, response) VALUES (?, ?)", (intent_id, r))

    conn.commit()
    conn.close()

init_db()
seed_data()

# ---------------- NLP PROCESS ----------------
def preprocess(text):
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    words = word_tokenize(text)
    return " ".join(words)

# ---------------- COLLEGE INFO ----------------
def get_college_info(field):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM college_info WHERE field=?", (field,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

# ---------------- AI MATCHING ----------------
def smart_match(user_message):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT p.pattern, r.response
        FROM patterns p
        JOIN responses r ON p.intent_id = r.intent_id
    """)
    data = c.fetchall()
    conn.close()

    if not data:
        return None, 0

    patterns = [row[0] for row in data]
    responses = [row[1] for row in data]

    vectorizer = TfidfVectorizer()
    vectors = vectorizer.fit_transform(patterns + [user_message])

    similarity = cosine_similarity(vectors[-1], vectors[:-1])
    best_index = similarity.argmax()
    confidence = similarity[0][best_index]

    if confidence > 0.3:
        return responses[best_index], confidence

    return None, confidence

# ---------------- CHATBOT RESPONSE ----------------
def get_response(message):
    text = message.lower()

    if "college name" in text:
        return get_college_info("name")
    if "address" in text:
        return get_college_info("address")
    if "phone" in text or "contact" in text:
        return get_college_info("phone")
    if "courses" in text:
        return get_college_info("courses")
    if "office" in text or "timing" in text:
        return get_college_info("office_time")

    reply, confidence = smart_match(message)

    if reply:
        return reply

    return "Sorry, I'm not sure about that. Can you rephrase your question?"

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    msg = data.get("message", "").strip()

    if not msg:
        return jsonify({"reply": "Please type a message."})

    if len(msg) > 200:
        return jsonify({"reply": "Message too long."})

    reply = get_response(msg)

    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO chats (user, bot) VALUES (?, ?)", (msg, reply))
    conn.commit()
    conn.close()

    return jsonify({"reply": reply})

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT password FROM admins WHERE username=?", (username,))
        row = c.fetchone()
        conn.close()

        if row and check_password_hash(row[0], password):
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        else:
            return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------- ADMIN PANEL ----------------
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")

        # DELETE INTENT
        if action == "delete":
            intent_id = request.form.get("intent_id")
            c.execute("DELETE FROM patterns WHERE intent_id=?", (intent_id,))
            c.execute("DELETE FROM responses WHERE intent_id=?", (intent_id,))
            c.execute("DELETE FROM intents WHERE id=?", (intent_id,))
            conn.commit()

        # ADD INTENT
        elif action == "add":
            tag = request.form["tag"].strip().lower()
            patterns = request.form["patterns"].split("\n")
            responses = request.form["responses"].split("\n")

            c.execute("INSERT INTO intents (tag) VALUES (?)", (tag,))
            intent_id = c.lastrowid

            for p in patterns:
                if p.strip():
                    c.execute("INSERT INTO patterns (intent_id, pattern) VALUES (?, ?)", (intent_id, p.strip()))

            for r in responses:
                if r.strip():
                    c.execute("INSERT INTO responses (intent_id, response) VALUES (?, ?)", (intent_id, r.strip()))

            conn.commit()

        # EDIT INTENT
        elif action == "edit":
            intent_id = request.form["intent_id"]
            tag = request.form["tag"].strip().lower()
            patterns = request.form["patterns"].split("\n")
            responses = request.form["responses"].split("\n")

            c.execute("UPDATE intents SET tag=? WHERE id=?", (tag, intent_id))
            c.execute("DELETE FROM patterns WHERE intent_id=?", (intent_id,))
            c.execute("DELETE FROM responses WHERE intent_id=?", (intent_id,))

            for p in patterns:
                if p.strip():
                    c.execute("INSERT INTO patterns (intent_id, pattern) VALUES (?, ?)", (intent_id, p.strip()))

            for r in responses:
                if r.strip():
                    c.execute("INSERT INTO responses (intent_id, response) VALUES (?, ?)", (intent_id, r.strip()))

            conn.commit()

        conn.close()
        return redirect(url_for("admin"))

    # FETCH INTENTS
    c.execute("""
        SELECT i.id, i.tag,
               GROUP_CONCAT(p.pattern, '\n'),
               GROUP_CONCAT(r.response, '\n')
        FROM intents i
        LEFT JOIN patterns p ON i.id = p.intent_id
        LEFT JOIN responses r ON i.id = r.intent_id
        GROUP BY i.id
    """)
    intents = c.fetchall()
    conn.close()

    return render_template("admin.html", intents=intents)

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run()
