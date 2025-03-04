import json
import os

def load_data(file_path):
    """Load existing data from a JSON file or return an empty dictionary."""
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    return {}

def save_data(data, file_path):
    """Save data to a JSON file."""
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

def clear_data(file_path):
    """Clear a JSON file by resetting it to an empty dictionary."""
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump({}, file, indent=4)
    print(f"Cleared {file_path}")