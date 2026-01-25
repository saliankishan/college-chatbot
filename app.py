from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
import random
import nltk
import string
from nltk.tokenize import word_tokenize
from nltk.stem import PorterStemmer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from werkzeug.security import generate_password_hash, check_password_hash
from time import time

login_attempts = {}

nltk.download("punkt")

app = Flask(__name__)
app.secret_key = "X9@kL#2026!AI$Chatbot"

stemmer = PorterStemmer()

# ---------------- DATABASE ----------------
def get_db():
    return sqlite3.connect("database.db")

def init_db():
    conn = get_db()
    c = conn.cursor()

    # Admins
    c.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)

    # Intents
    c.execute("""
        CREATE TABLE IF NOT EXISTS intents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag TEXT UNIQUE
        )
    """)

    # Patterns
    c.execute("""
        CREATE TABLE IF NOT EXISTS patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            intent_id INTEGER,
            pattern TEXT
        )
    """)

    # Responses
    c.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            intent_id INTEGER,
            response TEXT
        )
    """)

    # College info
    c.execute("""
        CREATE TABLE IF NOT EXISTS college_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            field TEXT UNIQUE,
            value TEXT
        )
    """)

    # Chats
    c.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            bot TEXT,
            time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ---------------- SEED ADMIN (RUN ONCE) ----------------
'''def seed_admin():
    conn = get_db()
    c = conn.cursor()

    username = "admin"
    password = "chatbot@777"
    password_hash = generate_password_hash(password)

    # DELETE old admin (force update)
    c.execute("DELETE FROM admins WHERE username=?", (username,))

    # INSERT fresh admin
    c.execute("INSERT INTO admins (username, password) VALUES (?, ?)",
              (username, password_hash))

    conn.commit()
    conn.close()
    print("✅ Admin reset successfully!")
  
seed_admin()  '''

# ---------------- SEED COLLEGE INFO ----------------
def seed_college_info():
    data = {
        "name": "Vijaya College, Mulki",
        "address": "Mulki, Karnataka",
        "phone": "9876543210",
        "courses": "BCA, BCom, BSc",
        "office_time": "9:30 AM to 4:30 PM"
    }
    conn = get_db()
    c = conn.cursor()
    for k, v in data.items():
        c.execute("INSERT OR IGNORE INTO college_info (field, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()

seed_college_info()

# ---------------- NLP PREPROCESS ----------------
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

# ---------------- CHATBOT ----------------
def get_response(message):
    text = message.lower()

    # Direct college info
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

    return "Sorry, I’m not sure about that. Can you rephrase your question?"

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    msg = data.get("message", "").strip()

    # 1️ Validate message length
    if not msg:
        return jsonify({"reply": "Please type a message."})

    if len(msg) > 100:
        return jsonify({"reply": "Message too long."})

    # 2️ Get chatbot reply
    reply = get_response(msg)

    # 3️ Safe database insert (SQL Injection safe ✅)
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO chats (user, bot) VALUES (?, ?)", (msg, reply))
        conn.commit()
        conn.close()
    except Exception as e:
        print("DB Error:", e)

    return jsonify({"reply": reply})


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    ip = request.remote_addr
    now = time()

    # limit attempts
    if ip in login_attempts and login_attempts[ip]["count"] >= 5 and now - login_attempts[ip]["time"] < 300:
        return "❌ Too many attempts. Try again after 5 minutes." #to prevent brute force hacking

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
            login_attempts[ip] = {"count": 0, "time": now}
            return redirect(url_for("admin"))
        else:
            if ip not in login_attempts:
                login_attempts[ip] = {"count": 0, "time": now}
            login_attempts[ip]["count"] += 1
            login_attempts[ip]["time"] = now
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

            c.execute("SELECT id FROM intents WHERE tag=?", (tag,))
            if c.fetchone():
                conn.close()
                return redirect(url_for("admin", error="Intent already exists"))

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

            # Update tag
            c.execute("UPDATE intents SET tag=? WHERE id=?", (tag, intent_id))

            # Delete old patterns & responses
            c.execute("DELETE FROM patterns WHERE intent_id=?", (intent_id,))
            c.execute("DELETE FROM responses WHERE intent_id=?", (intent_id,))

            # Insert updated patterns
            for p in patterns:
                if p.strip():
                    c.execute("INSERT INTO patterns (intent_id, pattern) VALUES (?, ?)", (intent_id, p.strip()))

            # Insert updated responses
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

    # REAL ANALYTICS
    c.execute("SELECT COUNT(*) FROM intents")
    total_intents = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM patterns")
    total_patterns = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM responses")
    total_responses = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM chats")
    total_chats = c.fetchone()[0]

    conn.close()

    error = request.args.get("error")
    return render_template(
        "admin.html",
        intents=intents,
        error=error,
        total_intents=total_intents,
        total_patterns=total_patterns,
        total_responses=total_responses,
        total_chats=total_chats
    )

if __name__ == "__main__":
    app.run()
