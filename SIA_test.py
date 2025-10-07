import json
import datetime
import tkinter as tk
from tkinter import ttk

# Setup
root = tk.Tk()
root.title("How Do You Feel?")
frm = ttk.Frame(root, padding=50)
frm.grid()


# Log file management
def open_log():
    return open("SIA_webside/common/log/log.txt", "a", encoding='utf-8')


def close_log(file_obj):
    if file_obj and not file_obj.closed:
        file_obj.close()


# Initialize counters
count_good = count_meh = count_bad = 0
good = tk.StringVar(value="Good: 0")
meh = tk.StringVar(value="Meh: 0")
bad = tk.StringVar(value="Bad: 0")


# Logging function
def write_to_log(file_obj, event_name, description, value):
    data = {
        "time": str(datetime.datetime.now()),
        "event": event_name,
        "details": description,
        "value": value
    }
    json.dump(data, file_obj, separators=(', ', ':'))
    file_obj.write('\n')
    file_obj.flush()  # Ensure data is written immediately


# Save summary to JSON
def save_summary():
    summary = {
        "good": count_good,
        "meh": count_meh,
        "bad": count_bad,
        "last_update": str(datetime.datetime.now())
    }
    with open("SIA_webside/common/json/summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=4, ensure_ascii=False)


# Update function
def update_label(feeling):
    global count_good, count_meh, count_bad
    log_file = open_log()

    if feeling == "good":
        count_good += 1
        good.set(f"Good: {count_good}")
        write_to_log(log_file, "Button", "Feeling", "good")
    elif feeling == "meh":
        count_meh += 1
        meh.set(f"Meh: {count_meh}")
        write_to_log(log_file, "Button", "Feeling", "meh")
    elif feeling == "bad":
        count_bad += 1
        bad.set(f"Bad: {count_bad}")
        write_to_log(log_file, "Button", "Feeling", "bad")
    elif feeling == "reset":
        count_good = count_meh = count_bad = 0
        good.set("Good: 0")
        meh.set("Meh: 0")
        bad.set("Bad: 0")
        write_to_log(log_file, "Button", "Input", "reset")

        # reset log file
        with open("SIA_webside/common/log/log.txt", "w", encoding="utf-8"):
            pass

    # Save the updated summary after each action
    save_summary()

    try:
        with open("SIA_webside/common/log/log.txt", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    print(json.loads(line))
    except FileNotFoundError:
        pass

    close_log(log_file)


ttk.Label(frm, text="How do you feel?").grid(column=1, row=0, pady=(0, 20))

ttk.Label(frm, textvariable=good).grid(column=0, row=2)
ttk.Label(frm, textvariable=meh).grid(column=1, row=2)
ttk.Label(frm, textvariable=bad).grid(column=2, row=2)

ttk.Button(frm, text="👍 Good", command=lambda: update_label("good")).grid(column=0, row=3, pady=10)
ttk.Button(frm, text="😐 Meh", command=lambda: update_label("meh")).grid(column=1, row=3, pady=10)
ttk.Button(frm, text="👎 Bad", command=lambda: update_label("bad")).grid(column=2, row=3, pady=10)
ttk.Button(frm, text="Reset", command=lambda: update_label("reset")).grid(column=1, row=4, pady=10)
ttk.Button(frm, text="Exit", command=root.destroy).grid(column=3, row=4, pady=10)

print(datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"))

root.mainloop()
