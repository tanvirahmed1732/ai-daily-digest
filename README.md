# AI Daily Digest

A small Python script that collects the day's AI news, uses Google Gemini to pick and summarize the 15–25 most important stories in plain English, and emails you a clean digest every day.

**Sources:** Hacker News, arXiv (cs.AI / cs.LG / cs.CL), Hugging Face Daily Papers, TechCrunch, Ars Technica, MIT Tech Review, The Verge, Wired, VentureBeat, KDnuggets, InfoQ, and the Google, OpenAI, Anthropic, DeepMind, Microsoft, Meta, Apple, AWS, BAIR and Hugging Face blogs.

**Cost:** Free. Gemini's free tier is enough. Claude is an optional paid backup.

---

## What you need

- A Windows, Mac or Linux computer that is on at least once a day
- Python 3.9 or newer
- A Gmail account to send the emails from (a separate one is recommended)
- A free Google Gemini API key

Setup takes about 15 minutes.

---

## Step 1: Install Python

**Windows**
1. Go to https://www.python.org/downloads/ and download the latest Python 3.
2. Run the installer. On the first screen, **tick "Add python.exe to PATH"** before clicking *Install Now*.
3. Open **Command Prompt** (press `Win`, type `cmd`, press Enter) and check it works:
   ```
   py -3 --version
   ```
   You should see something like `Python 3.13.x`.

**Mac / Linux**
Python 3 is usually preinstalled. Check with `python3 --version`. If it's missing, install it from python.org (Mac) or your package manager (Linux).

---

## Step 2: Get the project

Either download the ZIP from GitHub (green **Code** button, then **Download ZIP**, then unzip it), or clone it:
```
git clone https://github.com/<owner>/<repo>.git
```

Put the folder somewhere permanent, for example `C:\AI-Digest`. The daily schedule depends on this path, so don't move the folder later.

---

## Step 3: Install the required package

Open Command Prompt (or Terminal) **inside the project folder**.

*Windows tip:* open the folder in File Explorer, click the address bar, type `cmd` and press Enter.

Then run:

**Windows**
```
py -3 -m pip install -r requirements.txt
```
**Mac / Linux**
```
python3 -m pip install -r requirements.txt
```

---

## Step 4: Create a Gmail App Password

Gmail won't let scripts log in with your normal password. You need an **App Password**.

1. Sign in to the Gmail account that will **send** the digest.
2. Turn on 2-Step Verification if it isn't on already: https://myaccount.google.com/signinoptions/twosv
3. Open https://myaccount.google.com/apppasswords
4. Type a name such as `AI Digest` and click **Create**.
5. Copy the 16-character password it shows (e.g. `abcd efgh ijkl mnop`). **You only see it once.**

> If the App Passwords page says "not available", 2-Step Verification is not on yet, or the account is a work/school account whose admin has disabled it. Use a personal Gmail account instead.

---

## Step 5: Get a free Gemini API key

1. Go to https://aistudio.google.com/apikey and sign in with any Google account.
2. Click **Create API key** and copy it. It starts with `AIza...`.

*(Optional)* If you also have an Anthropic account, create a key at https://console.anthropic.com/. It's used only when Gemini is down. Without it, the script falls back to a simpler keyword-based selection on those days.

---

## Step 6: Create your `config.env`

1. In the project folder, make a copy of `config.env.example` and rename the copy to **`config.env`**.
   - *Windows:* if you can't see file extensions, in File Explorer click **View**, then **Show**, then **File name extensions**, so you don't end up with `config.env.txt`.
2. Open `config.env` in Notepad (or any text editor) and fill in:

| Setting | What to put | Example |
|---|---|---|
| `GMAIL_SENDER` | The Gmail address from Step 4 | `mydigest@gmail.com` |
| `GMAIL_APP_PASSWORD` | The 16-character App Password | `abcd efgh ijkl mnop` |
| `GMAIL_RECIPIENTS` | Who gets the email, comma-separated | `me@gmail.com,friend@yahoo.com` |
| `GEMINI_API_KEY` | Key from Step 5 | `AIzaSy...` |
| `ANTHROPIC_API_KEY` | Optional, leave blank if none | |
| `TIMEZONE_OFFSET_HOURS` | Your hours from UTC | `6` Bangladesh, `5.5` India, `0` UK, `-5` New York |
| `TIMEZONE_LABEL` | Optional name shown in the email | `Asia/Dhaka` |

Don't put quotes around the values. Save the file.

> **Keep `config.env` private.** It contains your email password and API keys. Never email it, upload it, or commit it to GitHub. The included `.gitignore` already stops git from uploading it.

---

## Step 7: Test it

In the project folder run:

**Windows:** `py -3 ai_digest.py`
**Mac / Linux:** `python3 ai_digest.py`

It takes 3–6 minutes. You'll see lines such as `HN: 18 items`, `TechCrunch AI: 20 items`, then `[gemini] success ...` and finally `Sent to [...]`. Check your inbox (and the Spam folder the first time. If it's there, mark it **Not spam**).

**It sends only once per day.** Running it again the same day just prints `Already sent today`. To force a re-send while testing, delete the `last_sent.txt` file.

---

## Step 8: Make it run automatically every day

### Windows, option A: run when the computer starts (simplest)
1. Right-click `run_startup.bat`, choose **Create shortcut**.
2. Press `Win + R`, type `shell:startup`, press Enter. A folder opens.
3. Move the shortcut into that folder.

Every time you log in, it waits 3 minutes (so Wi-Fi can connect) and then sends the digest, once per day at most. A small black window appears during the run. That's normal.

### Windows, option B: run at a fixed time (e.g. 8:00 AM)
1. Press `Win`, type **Task Scheduler**, open it.
2. Click **Create Basic Task…** and name it `AI Digest`.
3. Trigger: **Daily**, then pick a time.
4. Action: **Start a program**, then **Browse** to `run.bat` in the project folder.
5. **Important:** in the same screen, set **Start in (optional)** to the project folder path, e.g. `C:\AI-Digest`.
6. Finish. Then open the task's **Properties**, go to the **Settings** tab, and tick **"Run task as soon as possible after a scheduled start is missed"** so it still runs if the PC was off at that time.

You can use both A and B together. The once-per-day check prevents duplicates.

### Mac / Linux: cron
Run `crontab -e` and add (adjust the path and time):
```
0 8 * * * cd /path/to/AI-Digest && /usr/bin/python3 ai_digest.py >> bat_run.log 2>&1
```
This runs daily at 08:00. The computer must be on and awake at that time.

---

## Checking that it's working

- **`last_run.log`**: a line for every run, showing how many items each source returned and whether the email was sent.
- **`bat_run.log`**: full output, including any crash messages, when started from the `.bat` files.
- **`last_sent.txt`**: the date of the last successful send.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `'py' is not recognized` | Python isn't installed or wasn't added to PATH. Reinstall from python.org and tick **Add python.exe to PATH**. If you installed Python from the Microsoft Store, edit `run.bat` / `run_startup.bat` and replace `py -3` with `python`. |
| `ModuleNotFoundError: No module named 'requests'` | Redo Step 3. |
| `Missing ...config.env` | The file must be named exactly `config.env` (not `config.env.txt`) and be in the same folder as `ai_digest.py`. |
| `KeyError: 'GMAIL_SENDER'` (or another name) | That line is missing or misspelled in `config.env`. |
| `SMTPAuthenticationError` / `Username and Password not accepted` | You used your normal Gmail password, or the App Password was typed wrong. Create a new App Password (Step 4). `GMAIL_SENDER` must be the same account the App Password was created on. |
| Email arrives but says **"Heuristic mode"** at the bottom | Gemini failed that day (busy servers or a wrong key). Check `last_run.log` for `[gemini ...]` lines. `HTTP 400`/`403` means the key is wrong; `429`/`503` means Google was busy and it usually fixes itself. Adding `ANTHROPIC_API_KEY` gives a backup. |
| No email at all, nothing new in `last_run.log` | The scheduled task didn't run. For option A, check the shortcut is in `shell:startup`. For option B, check **Start in** is set, and look at the task's **History** tab. |
| A source always shows `0 items` | Normal for blogs that post rarely. Only posts from the last 48 hours are included. `HTTP 404` or `error:` lines mean that feed's address changed. Update or delete it in the `RSS_FEEDS` list inside `ai_digest.py`. |
| Email lands in Spam | Mark it **Not spam** once, or add the sender to your contacts. |

---

## Customizing

All in `ai_digest.py`:
- **News sources:** edit the `RSS_FEEDS` list (a display name plus the feed URL).
- **arXiv categories:** edit `cats` in `fetch_arxiv()`.
- **What the AI keeps or drops, number of items, writing style:** edit the text in `_build_prompt()`.
- **Email subject:** edit `msg["Subject"]` in `send_email()`.

---

## Files

| File | Purpose |
|---|---|
| `ai_digest.py` | The program |
| `config.env.example` | Template for your settings; copy it to `config.env` |
| `requirements.txt` | Python packages to install |
| `run.bat` | Windows: run once (for Task Scheduler) |
| `run_startup.bat` | Windows: waits 3 minutes, then runs (for the Startup folder) |
| `.gitignore` | Keeps `config.env` and log files out of GitHub |
