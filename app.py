import os
import sqlite3
import threading
import time
import hashlib
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from scraper import run_scraping_cycle

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "conferences.db")

def init_db():
    """Initializes the SQLite database and creates tables if they don't exist."""
    print("[Database] Initializing SQLite database...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create conferences table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            domain TEXT NOT NULL,
            start_date TEXT,
            end_date TEXT,
            location TEXT,
            description TEXT,
            url TEXT,
            source TEXT,
            verified INTEGER DEFAULT 0,
            flagged INTEGER DEFAULT 0,
            ai_reason TEXT,
            upvotes INTEGER DEFAULT 0,
            downvotes INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)
    
    # Create votes table to enforce unique voting
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conference_id INTEGER NOT NULL,
            device_id TEXT NOT NULL,
            ip_hash TEXT NOT NULL,
            vote_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (conference_id) REFERENCES conferences(id) ON DELETE CASCADE
        )
    """)
    
    # Create unique constraints
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_votes_device ON votes(conference_id, device_id)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_votes_ip ON votes(conference_id, ip_hash)")
    
    conn.commit()
    conn.close()
    print("[Database] Database initialized successfully.")


# Background Scheduler Thread
def start_scheduler():
    def scheduler_loop():
        # Let the server startup settle first before initial check
        time.sleep(5)
        print("[Scheduler] Background scraper thread started.")
        
        # Optionally: run a scraping cycle on startup if database is empty
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM conferences")
        count = c.fetchone()[0]
        conn.close()
        
        if count == 0:
            print("[Scheduler] Empty database detected. Running initial scrape cycle...")
            try:
                run_scraping_cycle(DB_PATH)
            except Exception as e:
                print(f"[Scheduler] Startup scrape failed: {e}")

        while True:
            now = datetime.now()
            # Target next midnight
            next_run = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
            delay_seconds = (next_run - now).total_seconds()
            print(f"[Scheduler] Next scheduled scrape at midnight: {next_run} (in {delay_seconds:.1f} seconds)")
            
            # Sleep in intervals so we don't block the system thread permanently
            while datetime.now() < next_run:
                time.sleep(30)
                
            print("[Scheduler] Midnight reached! Starting scheduled scrape cycle...")
            try:
                run_scraping_cycle(DB_PATH)
            except Exception as e:
                print(f"[Scheduler] Midnight scrape cycle failed: {e}")
                time.sleep(60)  # Avoid immediate infinite retry loops

    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()


# --- FRONTEND ROUTES ---

@app.route('/')
def index_page():
    """Renders the main conference directory page."""
    return render_template('index.html')

@app.route('/admin')
def admin_page():
    """Renders the admin dashboard page."""
    return render_template('admin.html')


# --- REST API ENDPOINTS ---

def get_hashed_ip():
    """Generates a stable, GDPR-compliant SHA-256 hash of the voter's IP address."""
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip and ',' in ip:
        ip = ip.split(',')[0].strip()
    
    # Use a secure salt to ensure hashes cannot be reversed to plain IP addresses
    salt = "conferenza_voter_salt_98765"
    return hashlib.sha256((ip + salt).encode('utf-8')).hexdigest()


# --- REST API ENDPOINTS ---

@app.route('/api/conferences', methods=['GET'])
def get_conferences():
    """
    Fetches clean/published conferences (where flagged = 0).
    Supports search query parameter and domain filter.
    Returns user_vote if a valid X-Device-ID header is sent.
    """
    search = request.args.get('search', '').strip()
    domain = request.args.get('domain', 'All').strip()
    device_id = request.headers.get('X-Device-ID', '').strip()
    ip_hash = get_hashed_ip()
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Fetch user's existing votes if device_id is provided
    user_votes = {}
    if device_id:
        cursor.execute("SELECT conference_id, vote_type FROM votes WHERE device_id = ? OR ip_hash = ?", (device_id, ip_hash))
        rows = cursor.fetchall()
        user_votes = {row['conference_id']: row['vote_type'] for row in rows}
        
    query = "SELECT * FROM conferences WHERE flagged = 0"
    params = []
    
    if domain != "All":
        query += " AND domain = ?"
        params.append(domain)
        
    if search:
        query += " AND (title LIKE ? OR description LIKE ? OR location LIKE ?)"
        params.append(f"%{search}%")
        params.append(f"%{search}%")
        params.append(f"%{search}%")
        
    # Order: verified first, then by upvotes desc, then by start date asc
    query += " ORDER BY verified DESC, upvotes DESC, start_date ASC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    confs = []
    for row in rows:
        conf_dict = dict(row)
        conf_dict['user_vote'] = user_votes.get(conf_dict['id'], None)
        confs.append(conf_dict)
        
    conn.close()
    return jsonify(confs)


@app.route('/api/conferences/<int:conf_id>/vote', methods=['POST'])
def vote_conference(conf_id):
    """
    Toggles, retracts, or submits a unique upvote/downvote for a conference card.
    Expects JSON: {"type": "up" | "down"} and "X-Device-ID" header.
    """
    data = request.json or {}
    vote_type = data.get('type')
    device_id = request.headers.get('X-Device-ID', '').strip()
    
    if not device_id:
        return jsonify({"error": "Missing unique device identifier (X-Device-ID header)."}), 400
        
    if vote_type not in ['up', 'down']:
        return jsonify({"error": "Invalid vote type. Must be 'up' or 'down'."}), 400
        
    ip_hash = get_hashed_ip()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Verify conference exists
    cursor.execute("SELECT flagged, upvotes, downvotes FROM conferences WHERE id = ?", (conf_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Conference not found"}), 404
        
    # 2. Check for existing vote by this device OR IP hash
    cursor.execute("SELECT id, vote_type FROM votes WHERE conference_id = ? AND (device_id = ? OR ip_hash = ?)", (conf_id, device_id, ip_hash))
    existing = cursor.fetchone()
    
    now_str = datetime.now().isoformat()
    action = None
    user_vote = None
    
    if not existing:
        # User has not voted yet on this conference -> Add new vote log
        cursor.execute("""
            INSERT INTO votes (conference_id, device_id, ip_hash, vote_type, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (conf_id, device_id, ip_hash, vote_type, now_str))
        
        # Increment counter
        col = 'upvotes' if vote_type == 'up' else 'downvotes'
        cursor.execute(f"UPDATE conferences SET {col} = {col} + 1 WHERE id = ?", (conf_id,))
        action = "added"
        user_vote = vote_type
        
    else:
        vote_record_id, existing_type = existing
        
        if existing_type == vote_type:
            # User clicked the SAME button again -> Retract/Remove vote
            cursor.execute("DELETE FROM votes WHERE id = ?", (vote_record_id,))
            
            # Decrement counter
            col = 'upvotes' if vote_type == 'up' else 'downvotes'
            cursor.execute(f"UPDATE conferences SET {col} = {col} - 1 WHERE id = ?", (conf_id,))
            action = "retracted"
            user_vote = None
            
        else:
            # User clicked the OPPOSITE button -> Toggle/Change vote
            cursor.execute("UPDATE votes SET vote_type = ?, device_id = ?, ip_hash = ?, created_at = ? WHERE id = ?", 
                           (vote_type, device_id, ip_hash, now_str, vote_record_id))
            
            # Update counters: decrement old, increment new
            if vote_type == 'up':
                cursor.execute("UPDATE conferences SET upvotes = upvotes + 1, downvotes = downvotes - 1 WHERE id = ?", (conf_id,))
            else:
                cursor.execute("UPDATE conferences SET upvotes = upvotes - 1, downvotes = downvotes + 1 WHERE id = ?", (conf_id,))
                
            action = "toggled"
            user_vote = vote_type
            
    conn.commit()
    
    # Fetch final updated counts
    cursor.execute("SELECT upvotes, downvotes FROM conferences WHERE id = ?", (conf_id,))
    up, down = cursor.fetchone()
    conn.close()
    
    return jsonify({
        "success": True,
        "action": action,
        "upvotes": up,
        "downvotes": down,
        "user_vote": user_vote
    })


# --- ADMIN API ENDPOINTS ---

@app.route('/api/admin/flagged', methods=['GET'])
def get_flagged_conferences():
    """Fetches all conferences flagged for admin review (where flagged = 1)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM conferences WHERE flagged = 1 ORDER BY created_at DESC")
    rows = cursor.fetchall()
    
    flagged_list = [dict(row) for row in rows]
    conn.close()
    
    return jsonify({
        "conferences": flagged_list,
        "gemini_active": bool(os.environ.get("GEMINI_API_KEY"))
    })


@app.route('/api/admin/approve/<int:conf_id>', methods=['POST'])
def approve_conference(conf_id):
    """Approves a flagged conference, setting verified = 1 and flagged = 0."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if exists
    cursor.execute("SELECT id FROM conferences WHERE id = ?", (conf_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"error": "Conference not found"}), 404
        
    # Set verified = 1 and flagged = 0
    cursor.execute("UPDATE conferences SET verified = 1, flagged = 0 WHERE id = ?", (conf_id,))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "Conference approved and verified."})


@app.route('/api/admin/reject/<int:conf_id>', methods=['POST'])
def reject_conference(conf_id):
    """Rejects a flagged conference, deleting it from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if exists
    cursor.execute("SELECT id FROM conferences WHERE id = ?", (conf_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"error": "Conference not found"}), 404
        
    cursor.execute("DELETE FROM conferences WHERE id = ?", (conf_id,))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "Conference rejected and deleted."})


@app.route('/api/admin/trigger-scrape', methods=['POST'])
def trigger_scrape():
    """Manually triggers the web scraping cycle."""
    try:
        new_c, flagged_c = run_scraping_cycle(DB_PATH)
        return jsonify({
            "success": True,
            "new_count": new_c,
            "flagged_count": flagged_c
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == '__main__':
    init_db()
    start_scheduler()
    # Run the Flask app on 0.0.0.0, port 5001
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)
