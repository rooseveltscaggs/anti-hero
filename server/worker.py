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
        if isinstance(value, bool):
            registry_entry.bool_value = value
        elif isinstance(value, (float, int)):
            registry_entry.int_value = value
        elif isinstance(value, str):
            registry_entry.string_value = value
        elif isinstance(value, datetime):
            registry_entry.datetime_value = value

    db_session.commit()
    db_session.close()
    return value

def retrieve_registry(key, default=None):
    registry_entry = db_session.query(RegistryEntry).filter(RegistryEntry.registry_name == key).first()
    if registry_entry:
        if registry_entry.int_value is not None:
            default = registry_entry.int_value
        
        if registry_entry.string_value is not None:
            default = registry_entry.string_value
        
        if registry_entry.bool_value is not None:
            default = registry_entry.bool_value
        
        if registry_entry.datetime_value is not None:
            default = registry_entry.datetime_value
    
    db_session.close() 
    return default

    
def send_heartbeat():
    while True:
        time.sleep(HEARTBEAT_INTERVAL)
        status = retrieve_registry("Status")
        in_backup = retrieve_registry("In_Backup")
        if status != 'Disabled' and not in_backup:
            partner_id = retrieve_registry("Partner_ID")
            if partner_id:
                partner = db_session.query(Server).filter(Server.id == partner_id).first()
                print("Sending heartbeat")
                try:
                    url = f'http://{partner.ip_address}:{partner.port}/heartbeat'
                    requests.request("PUT", url)
                except requests.exceptions.HTTPError as errh:
                    print ("Http Error:",errh)
                except requests.exceptions.ConnectionError as errc:
                    print ("Error Connecting:",errc)
                except requests.exceptions.Timeout as errt:
                    print ("Timeout Error:",errt)
                except requests.exceptions.RequestException as err:
                    print ("Oops: Something Else",err)
            else:
                print("No Heartbeat Sent: No partner found")
        db_session.close()

def request_authority():
    print("Failure detected! Requesting authority from Orchestrator")
    server_id = retrieve_registry("Server_ID")
    partner_id = retrieve_registry("Partner_ID")
    orc_ip = retrieve_registry("Orchestrator_IP")
    orc_port = retrieve_registry("Orchestrator_Port")
    curr_url = f'http://{orc_ip}:{orc_port}/failure?failed_server_id={partner_id}&backup_server_id={server_id}'
    
    while True:
        try:
            response = requests.request("PUT", curr_url)
            break
        except requests.exceptions.HTTPError as errh:
            print ("Http Error:",errh)
        except requests.exceptions.ConnectionError as errc:
            print ("Error Connecting:",errc)
        except requests.exceptions.Timeout as errt:
            print ("Timeout Error:",errt)
        except requests.exceptions.RequestException as err:
            print ("Oops: Something Else",err)

    if response.ok:
        store_registry("In_Backup", True)
        return True
    else:
        # Need to set self as failed and request recovery/healing
        return False

def update_authority():
    partner_id = retrieve_registry("Partner_ID")
    server_id = retrieve_registry("Server_ID")
    db_session.query(Inventory).filter(Inventory.location == partner_id, Inventory.is_dirty == False).update({Inventory.location: server_id}, synchronize_session = False)
    db_session.commit()
    db_session.close()
    return True

def attempt_recovery(relinquished_ids):
    print("Requesting Orchestrator to initiate recovery...")
    # Send initiate recovery request
    server_id = retrieve_registry("Server_ID")
    # partner_id = retrieve_registry("Partner_ID")
    orc_ip = retrieve_registry("Orchestrator_IP")
    orc_port = retrieve_registry("Orchestrator_Port")

    curr_url = f'http://{orc_ip}:{orc_port}/initiate-recovery'
    request_body = {}
    request_body["relinquished_ids"] = relinquished_ids
    request_body["server_id"] = server_id
    
    while True:
        try:
            response = requests.request("PUT", curr_url, json=request_body)
            break
        except requests.exceptions.HTTPError as errh:
            print ("Http Error:",errh)
        except requests.exceptions.ConnectionError as errc:
            print ("Error Connecting:",errc)
        except requests.exceptions.Timeout as errt:
            print ("Timeout Error:",errt)
        except requests.exceptions.RequestException as err:
            print ("Oops: Something Else",err)
    
    if response.ok:
        print("Recovery process approved by Orchestrator...returning to normal operation")
    return

def relinquish_inventory():
    server_id = retrieve_registry("Server_ID")
    query = db_session.query(Inventory).filter(Inventory.locked == False,
                                       Inventory.location == server_id)
    prev_relinquished_ids = db_session.query(Inventory).filter(Inventory.locked == False,
                                                      Inventory.location == 0,
                                                      Inventory.on_backup == True).all()
    # Get IDs of unlocked inventory (this will be requested later)
    relinquished_ids = query.all()
    relinquished_ids = [record.id for record in relinquished_ids]

    prev_relinquished_ids = [record.id for record in prev_relinquished_ids]


    # Move all unlocked inventory to Orchestrator with a special backup marker
    # to denote relinquished inventory
    query.update({ Inventory.location: 0, Inventory.activated: False, Inventory.on_backup: True })
    db_session.commit()
    return relinquished_ids + prev_relinquished_ids

def failure_detection():
    print("Background failure detection is running...")
    while True:
        time.sleep(HEARTBEAT_TIMEOUT)
        partner_id = retrieve_registry("Partner_ID")
        if partner_id:
            print("Checking for timeout")
            in_backup = retrieve_registry("In_Backup")
            status = retrieve_registry("Status")
            if not in_backup and status != "Disabled":
                # Check heartbeat
                last_heartbeat = retrieve_registry("Last_Heartbeat", datetime.utcnow())
                expiry = datetime.utcnow() - timedelta(seconds=HEARTBEAT_TIMEOUT)
                # In the instance of a self-failure, this expiry should already be passed
                if last_heartbeat < expiry:
                    authority = request_authority()
                    if authority:
                        print("Authority granted.. updating data")
                        update_authority()
                    else:
                        print("Authority denied... attempting recovery")
                        store_registry("Status", "Disabled")
                        relinquished_ids = relinquish_inventory()
                        attempt_recovery(relinquished_ids)
            db_session.close()
        else:
            print("No Timeout: No partner found...")


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
        time.sleep(60)
except KeyboardInterrupt:
    print("Exiting...")