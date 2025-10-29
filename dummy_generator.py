import os
import json
import random
from datetime import datetime, timedelta

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(BASE_DIR, exist_ok=True)

# --- Funktionen wie zuvor ---
def save_upload(year, month, day, upload_number, good, meh, bad, upload_ts):
    dir_path = os.path.join(BASE_DIR, year, month, day)
    os.makedirs(dir_path, exist_ok=True)
    data = {
        "upload_number": upload_number,
        "upload_Timestamp": upload_ts,
        "good": good,
        "meh": meh,
        "bad": bad,
        "good_Timestamp": upload_ts,
        "meh_Timestamp": upload_ts,
        "bad_Timestamp": upload_ts
    }
    file_path = os.path.join(dir_path, f"upload{upload_number}.json")
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)
    return dir_path

def update_totals(dir_path, good, meh, bad):
    totals_file = os.path.join(dir_path, "totals.json")
    if os.path.exists(totals_file):
        with open(totals_file, "r") as f:
            try:
                totals = json.load(f)
            except:
                totals = {"good":0, "meh":0, "bad":0}
    else:
        totals = {"good":0, "meh":0, "bad":0}

    totals["good"] += good
    totals["meh"] += meh
    totals["bad"] += bad

    with open(totals_file, "w") as f:
        json.dump(totals, f, indent=4)


# --- Monatsbasierte Maximalwerte ---
MONTH_MAX_VOTES = {
    1: (30, 80),   # Januar
    2: (40, 90),
    3: (50, 110),
    4: (60, 120),
    5: (80, 140),
    6: (100, 160),
    7: (90, 150),
    8: (80, 140),
    9: (60, 120),
    10: (50, 110),
    11: (40, 90),
    12: (30, 80)   # Dezember
}


def generate_dummy_data():
    start_date = datetime(2025, 1, 1)
    end_date = datetime.today()
    current_date = start_date

    while current_date <= end_date:
        year = current_date.strftime("%Y")
        month = current_date.month
        day = current_date.strftime("%d")

        min_votes, max_votes = MONTH_MAX_VOTES.get(month, (50, 140))
        total_votes = random.randint(min_votes, max_votes)
        remaining = total_votes

        for upload_number in range(1, 4):  # 3 Uploads pro Tag
            if upload_number < 3:
                good = random.randint(0, remaining)
                remaining -= good
                meh = random.randint(0, remaining)
                remaining -= meh
                bad = remaining
            else:
                good = remaining // 3
                meh = remaining // 3
                bad = remaining - good - meh

            upload_ts = current_date.replace(
                hour=random.randint(0,23),
                minute=random.randint(0,59),
                second=random.randint(0,59)
            ).strftime('%Y-%m-%d %H:%M:%S')

            dir_path = save_upload(year, f"{month:02}", day, upload_number, good, meh, bad, upload_ts)
            update_totals(dir_path, good, meh, bad)

        current_date += timedelta(days=1)

if __name__ == "__main__":
    generate_dummy_data()
    print("Realistischere Dummy-Daten für 2025 bis heute erstellt.")
