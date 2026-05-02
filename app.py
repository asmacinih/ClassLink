from flask import Flask, request, jsonify, session, send_from_directory
import sqlite3
import hashlib
import os
import re

app = Flask(__name__, static_folder="static")
app.secret_key = "change-this-to-a-random-string-before-going-live"

DB_PATH = os.path.join(os.path.dirname(__file__), "classlink.db")

# ── Database setup ──────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    UNIQUE NOT NULL,
            password    TEXT    NOT NULL,
            full_name   TEXT,
            grade       TEXT,
            school      TEXT,
            instagram   TEXT,
            tiktok      TEXT,
            snapchat    TEXT,
            discord     TEXT,
            phone       TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# ── Password helpers ─────────────────────────────────────────────────────────

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_password(password, hashed):
    return hash_password(password) == hashed

# ── Serve HTML pages ─────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "signin.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(".", filename)

# ── API: Sign up ─────────────────────────────────────────────────────────────

@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.get_json()
    username         = data.get("username", "").strip().lower()
    confirm_username = data.get("confirm_username", "").strip().lower()
    password         = data.get("password", "")
    confirm_password = data.get("confirm_password", "")

    if not username or not re.match(r"^[a-z0-9_]+$", username):
        return jsonify({"error": "Username can only contain letters, numbers, and underscores."}), 400
    if username != confirm_username:
        return jsonify({"error": "Usernames do not match."}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400
    if password != confirm_password:
        return jsonify({"error": "Passwords do not match."}), 400

    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, hash_password(password))
        )
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        return jsonify({"error": "That username is already taken."}), 409

    session["username"] = username
    return jsonify({"message": "Account created!", "username": username}), 201

# ── API: Profile setup ────────────────────────────────────────────────────────

@app.route("/api/profile", methods=["POST"])
def save_profile():
    if "username" not in session:
        return jsonify({"error": "Not logged in."}), 401
    data = request.get_json()
    conn = get_db()
    conn.execute("""
        UPDATE users SET
            full_name = ?, grade = ?, school = ?,
            instagram = ?, tiktok = ?, snapchat = ?, discord = ?, phone = ?
        WHERE username = ?
    """, (
        data.get("full_name", "").strip(),
        data.get("grade", "").strip(),
        data.get("school", "").strip(),
        data.get("instagram", "").strip(),
        data.get("tiktok", "").strip(),
        data.get("snapchat", "").strip(),
        data.get("discord", "").strip(),
        data.get("phone", "").strip(),
        session["username"]
    ))
    conn.commit()
    conn.close()
    return jsonify({"message": "Profile saved!"}), 200

# ── API: Sign in ─────────────────────────────────────────────────────────────

@app.route("/api/signin", methods=["POST"])
def signin():
    data = request.get_json()
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()

    if not user or not check_password(password, user["password"]):
        return jsonify({"error": "Incorrect username or password."}), 401

    session["username"] = username
    return jsonify({"message": "Signed in!", "username": username}), 200

# ── API: Sign out ─────────────────────────────────────────────────────────────

@app.route("/api/signout", methods=["POST"])
def signout():
    session.clear()
    return jsonify({"message": "Signed out."}), 200

# ── API: Current user ─────────────────────────────────────────────────────────

@app.route("/api/me", methods=["GET"])
def me():
    if "username" not in session:
        return jsonify({"error": "Not logged in."}), 401
    conn = get_db()
    user = conn.execute(
        "SELECT username, full_name, grade, school, instagram, tiktok, snapchat, discord, phone FROM users WHERE username = ?",
        (session["username"],)
    ).fetchone()
    conn.close()
    if not user:
        return jsonify({"error": "User not found."}), 404
    return jsonify(dict(user)), 200

# ── API: View any user's profile ──────────────────────────────────────────────

@app.route("/api/user/<username>", methods=["GET"])
def get_user(username):
    if "username" not in session:
        return jsonify({"error": "Not logged in."}), 401
    conn = get_db()
    user = conn.execute(
        "SELECT username, full_name, grade, school, instagram, tiktok, snapchat, discord, phone FROM users WHERE username = ?",
        (username.lower(),)
    ).fetchone()
    conn.close()
    if not user:
        return jsonify({"error": "User not found."}), 404
    return jsonify(dict(user)), 200

# ── API: Home feed ────────────────────────────────────────────────────────────

@app.route("/api/feed", methods=["GET"])
def feed():
    if "username" not in session:
        return jsonify({"error": "Not logged in."}), 401
    conn = get_db()
    me = conn.execute(
        "SELECT school FROM users WHERE username = ?", (session["username"],)
    ).fetchone()

    if me and me["school"]:
        users = conn.execute("""
            SELECT username, full_name, grade, school, instagram, tiktok, snapchat, discord, phone
            FROM users WHERE school = ? AND username != ?
            ORDER BY created_at DESC
        """, (me["school"], session["username"])).fetchall()
    else:
        users = conn.execute("""
            SELECT username, full_name, grade, school, instagram, tiktok, snapchat, discord, phone
            FROM users WHERE username != ?
            ORDER BY created_at DESC
        """, (session["username"],)).fetchall()

    conn.close()
    return jsonify([dict(u) for u in users]), 200

# ── API: Search ───────────────────────────────────────────────────────────────

@app.route("/api/search", methods=["GET"])
def search():
    if "username" not in session:
        return jsonify({"error": "Not logged in."}), 401
    query = request.args.get("q", "").strip().lower()
    if not query:
        return jsonify([]), 200
    conn = get_db()
    users = conn.execute("""
        SELECT username, full_name, grade, school, instagram, tiktok, snapchat, discord, phone
        FROM users WHERE (username LIKE ? OR full_name LIKE ?) AND username != ?
        ORDER BY username LIMIT 20
    """, (f"%{query}%", f"%{query}%", session["username"])).fetchall()
    conn.close()
    return jsonify([dict(u) for u in users]), 200

# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    print("\n  ClassLink is running!")
    print("  Open this in your browser: http://127.0.0.1:5000\n")
    app.run(debug=True, port=5001)
