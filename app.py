import os, csv, io, sqlite3
from datetime import date, datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response, abort
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-before-deployment")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "database", "attendance.db"))

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            register_no TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            class_name TEXT
        );
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            semester TEXT,
            teacher TEXT
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            attendance_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Present','Absent')),
            UNIQUE(student_id, subject_id, attendance_date),
            FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)
        admin = db.execute("SELECT id FROM admins LIMIT 1").fetchone()
        if not admin:
            db.execute("INSERT INTO admins(username,password_hash) VALUES(?,?)",
                       ("admin", generate_password_hash("admin123")))
        defaults = {"college_name": "Your College Name", "academic_year": "2026-2027"}
        for k, v in defaults.items():
            db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "admin_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def attendance_rate(student_id=None, subject_id=None):
    where, params = [], []
    if student_id:
        where.append("student_id=?"); params.append(student_id)
    if subject_id:
        where.append("subject_id=?"); params.append(subject_id)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with get_db() as db:
        row = db.execute(f"""SELECT SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END) present,
                                    COUNT(*) total FROM attendance{clause}""", params).fetchone()
    return round((row["present"] or 0) * 100 / row["total"], 1) if row["total"] else 0

@app.context_processor
def inject_globals():
    with get_db() as db:
        settings = {r["key"]: r["value"] for r in db.execute("SELECT key,value FROM settings")}
    return {"college": settings.get("college_name", "Your College Name"),
            "academic_year": settings.get("academic_year", "2026-2027")}

@app.route("/")
def index():
    return redirect(url_for("dashboard") if "admin_id" in session else url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with get_db() as db:
            admin = db.execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()
        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["admin_id"] = admin["id"]
            session["username"] = admin["username"]
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    today = date.today().isoformat()
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) n FROM students").fetchone()["n"]
        present = db.execute("SELECT COUNT(DISTINCT student_id) n FROM attendance WHERE attendance_date=? AND status='Present'", (today,)).fetchone()["n"]
        absent = max(total - present, 0)
        students = db.execute("SELECT id,name,register_no FROM students ORDER BY name").fetchall()
        risk = sum(1 for s in students if attendance_rate(s["id"]) < 75 and attendance_rate(s["id"]) > 0)
        recent = db.execute("""SELECT s.name student_name, sub.name subject_name, a.attendance_date, a.status
            FROM attendance a JOIN students s ON s.id=a.student_id JOIN subjects sub ON sub.id=a.subject_id
            ORDER BY a.attendance_date DESC,a.id DESC LIMIT 7""").fetchall()
        present_total = db.execute("SELECT COUNT(*) n FROM attendance WHERE status='Present'").fetchone()["n"]
        all_total = db.execute("SELECT COUNT(*) n FROM attendance").fetchone()["n"]
        monthly = db.execute("""SELECT substr(attendance_date,1,7) month,
            ROUND(100.0*SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END)/COUNT(*),1) rate
            FROM attendance GROUP BY substr(attendance_date,1,7) ORDER BY month DESC LIMIT 6""").fetchall()
    overall = round(present_total * 100 / all_total, 1) if all_total else 0
    labels = [r["month"] for r in reversed(monthly)]
    values = [r["rate"] for r in reversed(monthly)]
    return render_template("dashboard.html", total=total, present=present, absent=absent,
                           risk=risk, overall=overall, recent=recent, labels=labels, values=values)

@app.route("/students", methods=["GET", "POST"])
@login_required
def students():
    if request.method == "POST":
        data = [request.form.get(k, "").strip() for k in ("register_no","name","email","phone","class_name")]
        if not data[0] or not data[1]:
            flash("Register number and student name are required.", "danger")
        else:
            try:
                with get_db() as db:
                    db.execute("INSERT INTO students(register_no,name,email,phone,class_name) VALUES(?,?,?,?,?)", data)
                flash("Student added successfully.", "success")
            except sqlite3.IntegrityError:
                flash("Register number already exists.", "danger")
        return redirect(url_for("students"))
    q = request.args.get("q", "").strip()
    with get_db() as db:
        rows = db.execute("""SELECT * FROM students WHERE name LIKE ? OR register_no LIKE ?
                            ORDER BY name""", (f"%{q}%", f"%{q}%")).fetchall()
    return render_template("students.html", students=rows, query=q)

@app.route("/students/<int:sid>/edit", methods=["GET", "POST"])
@login_required
def edit_student(sid):
    with get_db() as db:
        student = db.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()
        if not student: abort(404)
        if request.method == "POST":
            data = [request.form.get(k, "").strip() for k in ("register_no","name","email","phone","class_name")]
            try:
                db.execute("UPDATE students SET register_no=?,name=?,email=?,phone=?,class_name=? WHERE id=?", (*data,sid))
                flash("Student updated.", "success")
                return redirect(url_for("students"))
            except sqlite3.IntegrityError:
                flash("Register number already exists.", "danger")
    return render_template("edit_student.html", student=student)

@app.route("/students/<int:sid>/delete", methods=["POST"])
@login_required
def delete_student(sid):
    with get_db() as db:
        db.execute("DELETE FROM students WHERE id=?", (sid,))
    flash("Student and related attendance records deleted.", "success")
    return redirect(url_for("students"))

@app.route("/subjects", methods=["GET", "POST"])
@login_required
def subjects():
    if request.method == "POST":
        data = [request.form.get(k, "").strip() for k in ("code","name","semester","teacher")]
        if not data[0] or not data[1]:
            flash("Subject code and name are required.", "danger")
        else:
            try:
                with get_db() as db:
                    db.execute("INSERT INTO subjects(code,name,semester,teacher) VALUES(?,?,?,?)", data)
                flash("Subject added successfully.", "success")
            except sqlite3.IntegrityError:
                flash("Subject code already exists.", "danger")
        return redirect(url_for("subjects"))
    q = request.args.get("q", "").strip()
    with get_db() as db:
        rows = db.execute("SELECT * FROM subjects WHERE name LIKE ? OR code LIKE ? ORDER BY name",
                          (f"%{q}%", f"%{q}%")).fetchall()
    return render_template("subjects.html", subjects=rows, query=q)

@app.route("/subjects/<int:sid>/edit", methods=["GET", "POST"])
@login_required
def edit_subject(sid):
    with get_db() as db:
        subject = db.execute("SELECT * FROM subjects WHERE id=?", (sid,)).fetchone()
        if not subject: abort(404)
        if request.method == "POST":
            data = [request.form.get(k, "").strip() for k in ("code","name","semester","teacher")]
            try:
                db.execute("UPDATE subjects SET code=?,name=?,semester=?,teacher=? WHERE id=?", (*data,sid))
                flash("Subject updated.", "success")
                return redirect(url_for("subjects"))
            except sqlite3.IntegrityError:
                flash("Subject code already exists.", "danger")
    return render_template("edit_subject.html", subject=subject)

@app.route("/subjects/<int:sid>/delete", methods=["POST"])
@login_required
def delete_subject(sid):
    with get_db() as db:
        db.execute("DELETE FROM subjects WHERE id=?", (sid,))
    flash("Subject and related attendance records deleted.", "success")
    return redirect(url_for("subjects"))

@app.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance():
    selected_date = request.values.get("attendance_date", date.today().isoformat())
    selected_subject = request.values.get("subject_id", "")
    with get_db() as db:
        subs = db.execute("SELECT * FROM subjects ORDER BY name").fetchall()
        if request.method == "POST":
            selected_subject = request.form.get("subject_id", "")
            selected_date = request.form.get("attendance_date", date.today().isoformat())
            if not selected_subject:
                flash("Please add/select a subject first.", "danger")
            else:
                for key, value in request.form.items():
                    if key.startswith("status_") and value in ("Present","Absent"):
                        student_id = key.split("_",1)[1]
                        db.execute("""INSERT INTO attendance(student_id,subject_id,attendance_date,status)
                            VALUES(?,?,?,?) ON CONFLICT(student_id,subject_id,attendance_date)
                            DO UPDATE SET status=excluded.status""",
                            (student_id, selected_subject, selected_date, value))
                flash("Attendance saved successfully.", "success")
            return redirect(url_for("attendance", attendance_date=selected_date, subject_id=selected_subject))
        students_rows = db.execute("""SELECT s.*,a.status FROM students s LEFT JOIN attendance a
            ON a.student_id=s.id AND a.subject_id=? AND a.attendance_date=? ORDER BY s.name""",
            (selected_subject or -1, selected_date)).fetchall()
    return render_template("attendance.html", students=students_rows, subjects=subs,
                           selected_date=selected_date, selected_subject=str(selected_subject))

@app.route("/analysis")
@login_required
def analysis():
    with get_db() as db:
        students_rows = db.execute("SELECT * FROM students ORDER BY name").fetchall()
        subjects_rows = db.execute("SELECT * FROM subjects ORDER BY name").fetchall()
        subject_stats = db.execute("""SELECT sub.name, COUNT(a.id) total,
            SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) present
            FROM subjects sub LEFT JOIN attendance a ON a.subject_id=sub.id GROUP BY sub.id ORDER BY sub.name""").fetchall()
        daily = db.execute("""SELECT attendance_date, ROUND(100.0*SUM(status='Present')/COUNT(*),1) rate
            FROM attendance GROUP BY attendance_date ORDER BY attendance_date DESC LIMIT 10""").fetchall()
    student_stats = []
    for s in students_rows:
        with get_db() as db:
            row = db.execute("""SELECT COUNT(*) total,SUM(status='Present') present FROM attendance WHERE student_id=?""",
                             (s["id"],)).fetchone()
        total = row["total"] or 0
        rate = round((row["present"] or 0)*100/total,1) if total else 0
        student_stats.append({"name":s["name"],"register_no":s["register_no"],"total":total,"rate":rate})
    return render_template("analysis.html", student_stats=student_stats, subject_stats=subject_stats, daily=daily)

@app.route("/reports")
@login_required
def reports():
    student_id = request.args.get("student_id","")
    subject_id = request.args.get("subject_id","")
    start = request.args.get("start","")
    end = request.args.get("end","")
    sql = """SELECT s.register_no,s.name student_name,sub.code,sub.name subject_name,
             a.attendance_date,a.status FROM attendance a
             JOIN students s ON s.id=a.student_id JOIN subjects sub ON sub.id=a.subject_id WHERE 1=1"""
    params=[]
    if student_id: sql += " AND s.id=?"; params.append(student_id)
    if subject_id: sql += " AND sub.id=?"; params.append(subject_id)
    if start: sql += " AND a.attendance_date>=?"; params.append(start)
    if end: sql += " AND a.attendance_date<=?"; params.append(end)
    sql += " ORDER BY a.attendance_date DESC,s.name"
    with get_db() as db:
        rows=db.execute(sql,params).fetchall()
        students_rows=db.execute("SELECT id,name FROM students ORDER BY name").fetchall()
        subjects_rows=db.execute("SELECT id,name FROM subjects ORDER BY name").fetchall()
    return render_template("reports.html", rows=rows, students=students_rows, subjects=subjects_rows,
                           filters={"student_id":student_id,"subject_id":subject_id,"start":start,"end":end})

@app.route("/reports/export.csv")
@login_required
def export_csv():
    # Reuse the same report filters.
    student_id=request.args.get("student_id",""); subject_id=request.args.get("subject_id","")
    start=request.args.get("start",""); end=request.args.get("end","")
    sql="""SELECT s.register_no,s.name,sub.code,sub.name,a.attendance_date,a.status
    FROM attendance a JOIN students s ON s.id=a.student_id JOIN subjects sub ON sub.id=a.subject_id WHERE 1=1"""
    params=[]
    for condition,value in [("s.id",student_id),("sub.id",subject_id)]:
        if value: sql+=f" AND {condition}=?"; params.append(value)
    if start: sql+=" AND a.attendance_date>=?"; params.append(start)
    if end: sql+=" AND a.attendance_date<=?"; params.append(end)
    sql+=" ORDER BY a.attendance_date DESC,s.name"
    with get_db() as db: rows=db.execute(sql,params).fetchall()
    output=io.StringIO(); writer=csv.writer(output)
    writer.writerow(["Register No","Student Name","Subject Code","Subject","Date","Status"])
    writer.writerows([tuple(r) for r in rows])
    response=make_response(output.getvalue())
    response.headers["Content-Disposition"]="attachment; filename=attendance_report.csv"
    response.headers["Content-Type"]="text/csv; charset=utf-8"
    return response

@app.route("/settings", methods=["GET","POST"])
@login_required
def settings():
    with get_db() as db:
        admin=db.execute("SELECT * FROM admins WHERE id=?",(session["admin_id"],)).fetchone()
        current={r["key"]:r["value"] for r in db.execute("SELECT key,value FROM settings")}
        if request.method=="POST":
            username=request.form.get("username","").strip()
            password=request.form.get("new_password","")
            if not username:
                flash("Username cannot be empty.","danger")
            else:
                try:
                    db.execute("UPDATE admins SET username=? WHERE id=?",(username,session["admin_id"]))
                    if password:
                        if len(password)<8:
                            flash("New password must contain at least 8 characters.","danger")
                            return render_template("settings.html",admin=admin,settings=current)
                        db.execute("UPDATE admins SET password_hash=? WHERE id=?",
                                   (generate_password_hash(password),session["admin_id"]))
                    for key in ("college_name","academic_year"):
                        db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                   (key,request.form.get(key,"").strip()))
                    session["username"]=username
                    flash("Settings updated successfully.","success")
                    return redirect(url_for("settings"))
                except sqlite3.IntegrityError:
                    flash("That username is already in use.","danger")
    return render_template("settings.html",admin=admin,settings=current)

@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", message="The page or record was not found."),404

@app.errorhandler(500)
def server_error(error):
    return render_template("error.html", message="Something went wrong. Please try again."),500

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)), debug=os.environ.get("FLASK_DEBUG")=="1")
