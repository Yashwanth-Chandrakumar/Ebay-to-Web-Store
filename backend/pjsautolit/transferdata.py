import json
import os
import threading

import django
from django.core.management import call_command
from django.db import connections

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pjsautolit.settings")
django.setup()

def dump_data():
    call_command('dumpdata', '--exclude', 'auth.permission', '--exclude', 'contenttypes', '--database', 'sqlite', '--output', 'data_dump.json')

def load_data(chunk):
    temp_filename = f"data_chunk_{chunk['index']}.json"
    with open(temp_filename, 'w') as f:
        json.dump(chunk['data'], f)
    call_command('loaddata', temp_filename)
    os.remove(temp_filename)

def split_data(filename, chunk_size):
    with open(filename, 'r') as f:
        data = json.load(f)
    
    chunks = []
    for i in range(0, len(data), chunk_size):
        chunks.append({
            'index': i // chunk_size,
            'data': data[i:i + chunk_size]
        })
    return chunks

def transfer_data():
    # Dump data from SQLite
    dump_data()
    
    # Split data into chunks
    chunks = split_data('data_dump.json', 1000)  # Adjust chunk size as needed
    
    # Create threads for each chunk
    threads = []
    for chunk in chunks:
        thread = threading.Thread(target=load_data, args=(chunk,))
        threads.append(thread)
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()

if __name__ == "__main__":
    transfer_data()
    print("Data transfer completed.")
