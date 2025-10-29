import os
import json

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
YEAR = "2025"  # Jahr, das zusammengefasst werden soll

def summarize_year_with_percent(year):
    year_dir = os.path.join(BASE_DIR, year)
    if not os.path.exists(year_dir):
        print(f"Kein Datenordner für {year} gefunden.")
        return

    year_totals = {"good": 0, "meh": 0, "bad": 0}
    year_days = 0
    month_summaries = {}

    for month in sorted(os.listdir(year_dir)):
        month_dir = os.path.join(year_dir, month)
        if not os.path.isdir(month_dir):
            continue

        month_totals = {"good": 0, "meh": 0, "bad": 0}
        month_days = 0

        for day in sorted(os.listdir(month_dir)):
            day_dir = os.path.join(month_dir, day)
            totals_file = os.path.join(day_dir, "totals.json")
            if os.path.exists(totals_file):
                with open(totals_file, "r") as f:
                    try:
                        totals = json.load(f)
                        for key in ["good", "meh", "bad"]:
                            month_totals[key] += totals.get(key, 0)
                        month_days += 1
                    except:
                        continue

        # Durchschnitt pro Tag
        month_avg = {key: (month_totals[key]/month_days if month_days>0 else 0) for key in ["good","meh","bad"]}
        # Prozentualer Anteil
        month_sum = sum(month_totals.values())
        month_percent = {key: (month_totals[key]/month_sum*100 if month_sum>0 else 0) for key in ["good","meh","bad"]}

        month_summaries[month] = {
            "totals": month_totals,
            "avg_per_day": month_avg,
            "percent": month_percent
        }

        for key in ["good","meh","bad"]:
            year_totals[key] += month_totals[key]
        year_days += month_days

    # Jahresdurchschnitt pro Tag
    year_avg = {key: (year_totals[key]/year_days if year_days>0 else 0) for key in ["good","meh","bad"]}
    # Jahresprozent
    year_sum = sum(year_totals.values())
    year_percent = {key: (year_totals[key]/year_sum*100 if year_sum>0 else 0) for key in ["good","meh","bad"]}

    print(f"Jahresübersicht für {year}:")
    print("Gesamtsummen:", year_totals)
    print("Durchschnitt pro Tag:", year_avg)
    print("Prozentualer Anteil:", year_percent)
    print("\nMonatsübersicht:")
    for month, data in month_summaries.items():
        print(f"{month}: Totals={data['totals']}, Durchschnitt pro Tag={data['avg_per_day']}, Prozent={data['percent']}")

if __name__ == "__main__":
    summarize_year_with_percent(YEAR)
