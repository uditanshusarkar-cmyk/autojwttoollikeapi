from flask import Flask, jsonify
import requests
import json
import time
import schedule
import os
import threading
import logging
from github import Github
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load environment variables
load_dotenv()
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# API URL
TOKEN_API_URL = "https://uditashu-jwt.vercel.app/token?uid={}&password={}"

# File paths
IND_JSON_FILE = "ind_ind.json"
TOKEN_JSON_FILE = "token_ind.json"

# Flask app
app = Flask(name)

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Maximum threads for parallel execution
MAX_THREADS = 50  
MAX_RETRIES = 3  # Number of retries for failed requests


def fetch_token(account):
    """Fetch JWT token for a single account with retries"""
    uid, password = account["uid"], account["password"]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(TOKEN_API_URL.format(uid, password), timeout=5)

            if response.status_code == 200:
                token_data = response.json()
                jwt_token = token_data.get("token")

                if jwt_token:
                    logging.info(f"✅ Generated JWT of {uid} (Attempt {attempt})")
                    return {"token": jwt_token}
                else:
                    logging.warning(f"⚠️ No token found for UID {uid} (Attempt {attempt})")

            else:
                logging.error(f"❌ Failed for UID {uid} (Status: {response.status_code}, Attempt {attempt})")

        except requests.exceptions.Timeout:
            logging.warning(f"⏳ Timeout for UID {uid} (Attempt {attempt})")

        except requests.exceptions.ConnectionError:
            logging.warning(f"🌐 Connection issue for UID {uid} (Attempt {attempt})")

        except Exception as e:
            logging.warning(f"⚠️ Error for UID {uid}: {e} (Attempt {attempt})")

        time.sleep(1)  # Small delay before retrying

    logging.error(f"❌ Skipping UID {uid} after {MAX_RETRIES} failed attempts")
    return None


def fetch_jwt_tokens():
    """Fetch JWT tokens in parallel and save them in the correct format"""
    try:
        with open(IND_JSON_FILE, "r") as f:
            accounts = json.load(f)

        logging.info(f"🚀 Fetching JWT tokens for {len(accounts)} accounts...")

        tokens = []
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            future_to_uid = {executor.submit(fetch_token, acc): acc["uid"] for acc in accounts}

            for future in as_completed(future_to_uid):
                result = future.result()
                if result:
                    tokens.append(result)

        # Save only if there are changes
        if os.path.exists(TOKEN_JSON_FILE):
            with open(TOKEN_JSON_FILE, "r") as f:
                existing_data = json.load(f)
            if existing_data == tokens:
                logging.info("✅ No changes in JWT tokens. Skipping GitHub upload.")
                return

        # Write new tokens
        with open(TOKEN_JSON_FILE, "w") as f:
            json.dump(tokens, f, indent=4)

        logging.info(f"✅ Saved {len(tokens)} JWT tokens to {TOKEN_JSON_FILE}")

        # Upload to GitHub
        upload_to_github()

    except Exception as e:
        logging.error(f"❌ Critical error: {e}")


def upload_to_github():
    """Upload token_ind.json to GitHub repo"""
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_user().get_repo(GITHUB_REPO)

        file_path = TOKEN_JSON_FILE
        contents = None

        try:
            contents = repo.get_contents(file_path)
        except Exception:
            pass  # File does not exist, so we will create it

        with open(TOKEN_JSON_FILE, "r") as f:
            file_content = f.read()
            if contents:
            repo.update_file(contents.path, "Updated JWT tokens", file_content, contents.sha)
            logging.info("✅ Updated token_ind.json on GitHub")
        else:
            repo.create_file(file_path, "Added JWT tokens", file_content)
            logging.info("✅ Uploaded token_ind.json to GitHub")

    except Exception as e:
        logging.error(f"❌ GitHub upload error: {e}")


@app.route("/")
def home():
    return jsonify({"message": "Super Fast JWT Fetcher is running!"})


@app.route("/run-job", methods=["GET"])
def run_job():
    fetch_jwt_tokens()
    return jsonify({"message": "✅ JWT tokens updated!"})


def schedule_task():
    """Runs the fetch function every hour in a separate thread"""
    schedule.every(1).hour.do(fetch_jwt_tokens)
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


# Run schedule in background
threading.Thread(target=schedule_task, daemon=True).start()

if name == "main":
    fetch_jwt_tokens()  # Run immediately on start
    app.run(host="0.0.0.0", port=5000, debug=True)