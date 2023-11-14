import threading
import time
from pydantic import BaseModel
from typing import List, Annotated, Optional
from datetime import datetime, timedelta
import socket
from database import db_session, engine
import models
import requests
import time
from models import Server, Inventory, Reservation, RegistryEntry

HEARTBEAT_TIMEOUT = 10
HEARTBEAT_INTERVAL = 2

def store_registry(key, value):
    registry_entry = db_session.query(RegistryEntry).filter(RegistryEntry.registry_name == key).first()
    if not registry_entry:
        registry_entry = RegistryEntry(registry_name=key)
        db_session.add(registry_entry)

    if value is None:
        registry_entry.int_value = None
        registry_entry.string_value = None
        registry_entry.bool_value = None
        registry_entry.datetime_value = None
    else:
        if isinstance(value, int):
            registry_entry.int_value = value
        if isinstance(value, str):
            registry_entry.string_value = value
        if isinstance(value, bool):
            registry_entry.bool_value = value
        if isinstance(value, datetime):
            registry_entry.datetime_value = value
    

    db_session.commit()
    db_session.close()
    return value

def retrieve_registry(key, default=None):
    registry_entry = db_session.query(RegistryEntry).filter(RegistryEntry.registry_name == key).first()
    if registry_entry:
        if registry_entry.int_value is not None:
            return registry_entry.int_value
        
        if registry_entry.string_value is not None:
            return registry_entry.string_value
        
        if registry_entry.bool_value is not None:
            return registry_entry.bool_value
        
        if registry_entry.datetime_value is not None:
            return registry_entry.datetime_value
        
    return default
    
def send_heartbeat():
    while True:
        time.sleep(HEARTBEAT_INTERVAL)
        status = retrieve_registry("Status")
        if status != 'Disabled':
            partner_id = retrieve_registry("Partner_ID")
            if partner_id:
                partner = db_session.query(Server).filter(Server.id == partner_id).first()
                print("Sending heartbeat")
                url = f'http://{partner.ip_address}:{partner.port}/heartbeat'
                requests.request("PUT", url)
            else:
                print("No partner found")

def request_authority():
    server_id = retrieve_registry("Server_ID")
    partner_id = retrieve_registry("Partner_ID")
    orc_ip = retrieve_registry("Orchestrator_IP")
    orc_port = retrieve_registry("Orchestrator_Port")
    curr_url = f'http://{orc_ip}:{orc_port}/failure?failed_server={partner_id}&backup_server={server_id}'
    response = requests.request("PUT", curr_url)
    if response.ok:
        store_registry("In_Backup", True)
        return True
    else:
        return False

def update_authority():
    partner_id = retrieve_registry("Partner_ID")
    server_id = retrieve_registry("Server_ID")
    db_session.query(Inventory).filter(Inventory.location == partner_id).update({Inventory.location: server_id, Inventory.on_backup: True}, synchronize_session = False)
    db_session.commit()
    return True

def failure_detection():
    while True:
        print("Background failure detection is running...")
        time.sleep(HEARTBEAT_TIMEOUT)
        in_backup = retrieve_registry("In_Backup")
        status = retrieve_registry("Status")
        if not in_backup and status != "Disabled":
            # Check heartbeat
            expiry = datetime.utcnow() - timedelta(seconds=HEARTBEAT_TIMEOUT)
            last_heartbeat = retrieve_registry("Last_Heartbeat", datetime.utcnow())
            if last_heartbeat < expiry:
                authority = request_authority()
            if authority:
                update_authority()
        db_session.close()


        # Send heartbeat
        # Check for received heartbeat
        # Request authority from orchestrator
        # Update DB to show new location for taken inventory

# Start the background worker in a separate thread
worker_thread = threading.Thread(target=failure_detection)
worker_thread2 = threading.Thread(target=send_heartbeat)
worker_thread.daemon = True  # This allows the worker thread to exit when the main program ends
worker_thread2.daemon = True  # This allows the worker thread to exit when the main program ends
worker_thread.start()
worker_thread2.start()

# Main program
try:
    while True:
        print("Main program is running...")
        time.sleep(2)
except KeyboardInterrupt:
    print("Exiting...")