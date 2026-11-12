# Smart Attendance Analyser

A full-stack attendance management website built with Python Flask, SQLite, HTML, CSS, JavaScript, Bootstrap and Chart.js.

## Features
- Admin login and session protection
- Student add, search, edit and delete
- Subject add, search, edit and delete
- Date- and subject-wise attendance with duplicate prevention and update
- Dashboard statistics and charts calculated from database records
- Student/subject/daily attendance analysis and at-risk indicator (below 75%)
- Filterable attendance reports, CSV export and browser print/PDF
- Admin username/password and college settings

## Demo login
- Username: `admin`
- Password: `admin123`

Change this password from **Settings** before putting the website online.

## Run locally (Windows)
1. Install Python 3.10 or newer from https://www.python.org/downloads/ . During setup, select **Add Python to PATH**.
2. Extract this ZIP file.
3. Open the extracted `smart_attendance_analyser` folder.
4. In that folder, open Command Prompt/Terminal.
5. Run:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

6. Open `http://127.0.0.1:5000` in your browser.
7. Login with `admin` / `admin123`.

Mac/Linux activation: `source venv/bin/activate`.

## First-use sequence
1. Open **Settings** and change the default password and college details.
2. Open **Students** and add students with unique register numbers.
3. Open **Subjects** and add subjects with unique subject codes.
4. Open **Mark Attendance**, select date and subject, mark each student Present or Absent, and save.
5. Open **Dashboard**, **Analysis** and **Reports** to see database-backed information.

## GitHub upload
1. Create a new empty repository on GitHub.
2. Extract this ZIP.
3. Upload the contents of the `smart_attendance_analyser` folder (not the ZIP itself) to the repository, or use Git:

```bash
git init
git add .
git commit -m "Initial Smart Attendance Analyser project"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
git push -u origin main
```

Do not upload your real database or secrets. `.gitignore` excludes SQLite database files.

## Deploy on Render
1. Push the project to GitHub.
2. In Render, choose **New +** → **Blueprint** and connect the repository. Render reads `render.yaml`.
3. Wait for deployment, then open the generated `onrender.com` URL.
4. Login with the demo credentials and immediately change the password.

**Database persistence:** `render.yaml` configures a 1 GB persistent disk at `/var/data`. Render persistent disks may require a paid service plan. If you deploy on a plan without persistent-disk support, SQLite data may be lost when the service restarts/redeploys. For a permanent public deployment, use a Render plan that supports persistent disks or switch to a managed PostgreSQL database.

## Important notes
- The charts use Chart.js from a CDN, so an internet connection is needed for charts and Bootstrap styling.
- CSV export is available in Reports. Use **Print Report** and choose **Save as PDF** in the browser's print dialog to create a PDF.
- The app creates `database/attendance.db` automatically on first run.
- For production, set a strong random `SECRET_KEY` environment variable.
