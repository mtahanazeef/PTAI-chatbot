## 1. Install MySQL (if you don't have it already)

- Windows/Mac: install **MySQL Community Server** from
  https://dev.mysql.com/downloads/mysql/
- During setup, set a root password and remember it.

## 2. Create the database

Open a terminal and log into MySQL:

```bash
mysql -u root -p
```

Then run:

```sql
CREATE DATABASE ptai_db;
```

That's it — the app creates the `users` and `chat_history` tables
automatically the first time it runs.

## 3. Set your MySQL password in app.py

Open `app.py` and find this block near the top:

```python
MYSQL_CONFIG = {
    "host": os.environ.get("PTAI_DB_HOST", "localhost"),
    "user": os.environ.get("PTAI_DB_USER", "root"),
    "password": os.environ.get("PTAI_DB_PASSWORD", "YOUR_MYSQL_PASSWORD"),
    "database": os.environ.get("PTAI_DB_NAME", "ptai_db"),
}
```

Replace `YOUR_MYSQL_PASSWORD` with the root password you set in step 1.
(Or, better: set it as an environment variable instead of editing the file —
see the note at the bottom.)

## 4. Install Python dependencies

From inside the project folder:

```bash
pip install -r requirements.txt
```

If you're on a system that requires it:

```bash
pip install -r requirements.txt --break-system-packages
```

## 5. Run the app

```bash
python app.py
```

You should see:

```
--- Starting PTAI Web Server ---
--- AI configured successfully using gemini-flash-latest ---
Ensure VPN is ON if required.
 * Running on http://127.0.0.1:5000
```

Open **http://127.0.0.1:5000** in your browser.

## 6. Using it

- You can chat right away as a guest — nothing is saved.
- Click **Sign in** (top right) → **Sign up** to create an account.
- Once logged in, every chat exchange is saved to MySQL under your account.
- Click the **My Chats** tab to see your saved history; click any entry to
  bring it back into the chat window.
- The moon/sun icon next to your account button switches between dark and
  light mode — your choice is remembered on that browser.

## Troubleshooting

- **"Access denied for user 'root'@'localhost'"** → your MySQL password in
  `app.py` doesn't match. Double-check step 3.
- **"Unknown database 'ptai_db'"** → you skipped step 2, or used a different
  database name — make sure `MYSQL_CONFIG["database"]` matches what you
  created.
- **AI not responding / "System Error: AI offline"** → your Gemini key may
  be rate-limited, region-restricted, or expired. The original app notes you
  may need a VPN on for this — same applies here.
- **Weather cards not loading** → OpenWeatherMap key issue, or no internet.

## Optional: keep secrets out of the code

Right now your API keys and MySQL password live directly in `app.py`, same
as your original file. That's fine to get running, but if you ever share
this code (e.g. push to GitHub), anyone can see those keys. A safer pattern,
when you're ready:

```bash
export PTAI_DB_PASSWORD="your_real_password"
export PTAI_SECRET_KEY="some_long_random_string"
```

and the app will pick those up automatically instead of the hardcoded
defaults (the Gemini/weather keys can be moved the same way if you'd like —
just ask and I'll wire it up).
