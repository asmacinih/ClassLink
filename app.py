from flask import Flask, request, jsonify, session, send_from_directory
import hashlib
import os
import re

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

# ── Database backend detection ────────────────────────────────────────────────
# Uses PostgreSQL on Render (DATABASE_URL set), SQLite locally.

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    import psycopg2
    import psycopg2.extras
    # Render provides postgres:// but psycopg2 requires postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    import sqlite3
    DB_PATH = os.path.join(os.path.dirname(__file__), "classlink.db")

# ── Database helpers ──────────────────────────────────────────────────────────

def query(sql, params=(), one=False, write=False):
    """Run a SQL query against whichever DB backend is configured.
    Returns a dict (one=True), list of dicts (one=False), or None (write=True).
    Always uses ? as the placeholder — automatically converted to %s for Postgres.
    """
    if DATABASE_URL:
        sql_pg = sql.replace("?", "%s")
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql_pg, params)
                    if write:
                        return None
                    if one:
                        row = cur.fetchone()
                        return dict(row) if row else None
                    return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(sql, params)
            if write:
                conn.commit()
                return None
            if one:
                row = cur.fetchone()
                return dict(row) if row else None
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()


def init_db():
    if DATABASE_URL:
        query("""
            CREATE TABLE IF NOT EXISTS users (
                id          SERIAL PRIMARY KEY,
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
                avatar_url  TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """, write=True)
        # Add avatar_url to existing databases that predate this column
        query("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT", write=True)
    else:
        query("""
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
                avatar_url  TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """, write=True)
        # Add avatar_url to existing SQLite databases
        try:
            query("ALTER TABLE users ADD COLUMN avatar_url TEXT", write=True)
        except Exception:
            pass  # Column already exists


# Run at startup (covers both gunicorn on Render and local dev)
with app.app_context():
    init_db()

# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_password(password, hashed):
    return hash_password(password) == hashed

# ── Serve HTML pages ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "signin.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(".", filename)

# ── API: Sign up ──────────────────────────────────────────────────────────────

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
        query(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, hash_password(password)),
            write=True
        )
    except Exception as e:
        if "unique" in str(e).lower():
            return jsonify({"error": "That username is already taken."}), 409
        raise

    session["username"] = username
    return jsonify({"message": "Account created!", "username": username}), 201

# ── API: Profile setup ────────────────────────────────────────────────────────

@app.route("/api/profile", methods=["POST"])
def save_profile():
    if "username" not in session:
        return jsonify({"error": "Not logged in."}), 401
    data = request.get_json()
    query("""
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
    ), write=True)
    return jsonify({"message": "Profile saved!"}), 200

# ── API: Upload avatar ────────────────────────────────────────────────────────

@app.route("/api/upload-avatar", methods=["POST"])
def upload_avatar():
    if "username" not in session:
        return jsonify({"error": "Not logged in."}), 401
    data = request.get_json()
    avatar_data = data.get("avatar_data", "").strip()

    if not avatar_data:
        return jsonify({"error": "No image data provided."}), 400
    if not avatar_data.startswith("data:image/"):
        return jsonify({"error": "Invalid image format."}), 400
    # Limit to ~2MB (base64 encoded ~2.7MB raw)
    if len(avatar_data) > 2_800_000:
        return jsonify({"error": "Image is too large. Please use an image under 2MB."}), 400

    query(
        "UPDATE users SET avatar_url = ? WHERE username = ?",
        (avatar_data, session["username"]),
        write=True
    )
    return jsonify({"message": "Avatar uploaded!", "avatar_url": avatar_data}), 200

# ── API: Sign in ──────────────────────────────────────────────────────────────

@app.route("/api/signin", methods=["POST"])
def signin():
    data = request.get_json()
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")

    user = query("SELECT * FROM users WHERE username = ?", (username,), one=True)

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
    user = query(
        "SELECT username, full_name, grade, school, instagram, tiktok, snapchat, discord, phone, avatar_url FROM users WHERE username = ?",
        (session["username"],), one=True
    )
    if not user:
        return jsonify({"error": "User not found."}), 404
    return jsonify(user), 200

# ── API: View any user's profile ──────────────────────────────────────────────

@app.route("/api/user/<username>", methods=["GET"])
def get_user(username):
    if "username" not in session:
        return jsonify({"error": "Not logged in."}), 401
    user = query(
        "SELECT username, full_name, grade, school, instagram, tiktok, snapchat, discord, phone, avatar_url FROM users WHERE username = ?",
        (username.lower(),), one=True
    )
    if not user:
        return jsonify({"error": "User not found."}), 404
    return jsonify(user), 200

# ── API: Home feed ────────────────────────────────────────────────────────────

@app.route("/api/feed", methods=["GET"])
def feed():
    if "username" not in session:
        return jsonify({"error": "Not logged in."}), 401
    me = query("SELECT school FROM users WHERE username = ?", (session["username"],), one=True)

    if me and me["school"]:
        users = query("""
            SELECT username, full_name, grade, school, instagram, tiktok, snapchat, discord, phone, avatar_url
            FROM users WHERE school = ? AND username != ?
            ORDER BY created_at DESC
        """, (me["school"], session["username"]))
    else:
        users = query("""
            SELECT username, full_name, grade, school, instagram, tiktok, snapchat, discord, phone, avatar_url
            FROM users WHERE username != ?
            ORDER BY created_at DESC
        """, (session["username"],))

    return jsonify(users), 200

# ── API: Search ───────────────────────────────────────────────────────────────

@app.route("/api/search", methods=["GET"])
def search():
    if "username" not in session:
        return jsonify({"error": "Not logged in."}), 401
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify([]), 200
    users = query("""
        SELECT username, full_name, grade, school, instagram, tiktok, snapchat, discord, phone, avatar_url
        FROM users WHERE (username LIKE ? OR full_name LIKE ?) AND username != ?
        ORDER BY username LIMIT 20
    """, (f"%{q}%", f"%{q}%", session["username"]))
    return jsonify(users), 200

# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n  ClassLink is running!")
    print("  Open this in your browser: http://127.0.0.1:5001\n")
    app.run(debug=True, port=5001)
