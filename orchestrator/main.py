from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Annotated, Optional
from datetime import datetime, timedelta
import socket
from database import db_session, engine
import models
import requests
import time
import string
import collections
import random
from models import Server, Inventory, Reservation, RegistryEntry

app = FastAPI()
models.Base.metadata.create_all(bind=engine)

TRANSACT_ID_LENGTH = 10

def generate_random_string(length):
    characters = string.ascii_letters + string.digits
    random_string = ''.join(random.choice(characters) for _ in range(length))
    return random_string

def update_server_status(server_id):
    server = db_session.query(Server).filter(Server.id == server_id).first()
    if server:
        url = f'http://{server.ip_address}:{server.port}/status'
        response = requests.get(url)
        if response.ok:
            # If the response status code is 200 (OK), parse the response as JSON
            json_data = response.json()
            server.status = json_data['status']
            server.last_updated = datetime.utcnow()
    db_session.close()

@app.get("/status")
def server_status():
    return {"status": "Available", "is_orchestrator": True}

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
            return registry_entry.int_value
        
        if registry_entry.string_value is not None:
            return registry_entry.string_value
        
        if registry_entry.bool_value is not None:
            return registry_entry.bool_value
        
        if registry_entry.datetime_value is not None:
            return registry_entry.datetime_value
        
    return default


@app.post("/autoregister")
def auto_register(request: Request, background_tasks: BackgroundTasks, hostname: Optional[str] = None, port: Optional[str] = "80"):
    host_ip = request.client.host
    server = db_session.query(Server).filter(Server.hostname==hostname, Server.ip_address==host_ip, Server.port==port).first()
    if not server:
        server = Server(hostname=hostname, ip_address=host_ip, port=port)
        db_session.add(server)
        db_session.commit()
        server = server.as_dict()
        db_session.close()
        # return {"host_ip": host_ip, "hostname": hostname, "server_id": server.id}
    servers = db_session.query(Server).all()
    for server_obj in servers:
        background_tasks.add_task(send_server_map, server_obj.id)
    return server

@app.put("/servers/sync")
def sync_all_servers(background_tasks: BackgroundTasks):
    servers = db_session.query(Server).all()
    for server_obj in servers:
        background_tasks.add_task(send_server_map, server_obj.id)
        background_tasks.add_task(send_inventory, server_obj.id)
    db_session.close()
    return {"Status": "Queued"}

@app.get("/servers")
def get_servers():
    servers = db_session.query(Server).all()
    return servers

@app.post("/servers")
def create_server(host_ip: str, request: Request, background_tasks: BackgroundTasks, hostname: Optional[str] = None, port: Optional[str] = "80"):
    server = Server(hostname=hostname, host_ip=host_ip, port=port)
    db_session.add(server)
    db_session.commit()
    db_session.close()
    servers = db_session.query(Server).all()
    for server_obj in servers:
        background_tasks.add_task(send_server_map, server_obj.id)
    return {"host_ip": host_ip, "hostname": hostname, "server_id": server.id}


@app.put("/pair")
def pair_servers(server1_id: int, server2_id: int, background_tasks: BackgroundTasks):
    server1 = db_session.query(Server).filter(Server.id == server1_id).first()
    server2 = db_session.query(Server).filter(Server.id == server2_id).first()
    if server1 and server2:
        server1_url = f'http://{server1.ip_address}:{server1.port}/partner?partner_id={server2_id}'
        response = requests.request("PUT", server1_url)
        if response.ok:
            server2_url = f'http://{server2.ip_address}:{server2.port}/partner?partner_id={server1_id}'
            response = requests.request("PUT", server2_url)
            if response.ok:
                server1.partner_id = server2_id
                server2.partner_id = server1_id
        db_session.commit()
        db_session.close()
        background_tasks.add_task(send_inventory, server1_id)
        background_tasks.add_task(send_inventory, server2_id)
        return {"Status": "Paired"}
    else:
        return {"Status": "Server(s) not found"}

@app.get("/server/{server_id}")
def get_server_status(server_id: int):
    update_server_status(server_id)
    server = db_session.query(Server).filter(Server.id == server_id).first()
    if server:
        return server
    else:
        return None

@app.get("/inventory")
def get_inventory_map():
    db_session.commit()
    inventory = db_session.query(Inventory).all()
    return inventory

@app.get("/latency/{nil}")
def latency_test(nil: Optional[str]):
    return {"row":"1","section":"101","seat":"1","location":1,"availability":"Available","transaction_id":None,"is_dirty":False,"desirability":8,"id":1,"price":457,"description":None,"on_backup":False}

@app.get("/inventory/{item_id}")
def get_item_status(item_id: int):
    db_session.commit()
    inventory = db_session.query(Inventory).filter(Inventory.id == item_id).first()
    return inventory

@app.put("/inventory/transfer")
def initiate_transfer(ids: List[int], destination: int, background_tasks: BackgroundTasks):
    # data = request.json()
    # ids = data['ids']
    # Event.resource_id == row.id) & (Event.weekday.contains(weekdayAbbrev[i])) & (Event.recurrence_type.in_(['Weekly', 'Monthly'])
    # session.query(Table.column, 
#    func.count(Table.column)).group_by(Table.column).all()
    locations = db_session.query(Inventory.location).filter(Inventory.id.in_(ids)).group_by(Inventory.location).all()
    for location in locations:
        inventory_ids = db_session.query(Inventory.id).filter(Inventory.location == location[0], Inventory.id.in_(ids)).all()
        inventory_ids = [record[0] for record in inventory_ids]
        print("-- Inventory Transfer -- ")
        # print(inventory_ids)
        print(f'Inititating transfer of array length {len(inventory_ids)} with ids {inventory_ids[0]} ... {inventory_ids[len(inventory_ids)-1]}')
        background_tasks.add_task(transfer_inventory, inventory_ids, location[0], destination)
    
    return {"Status": "Queued"}

@app.put("/failure")
def report_failure(failed_server_id: int, backup_server_id: int):
    failed_server = db_session.query(Server).filter(Server.id == failed_server_id).first()
    backup_server = db_session.query(Server).filter(Server.id == backup_server_id).first()
    if failed_server and backup_server:
        if not backup_server.in_failure and not failed_server.in_backup:
            failed_server.in_failure = True
            backup_server.in_backup = True
            db_session.commit()
        else:
            bad_resp = {"Status": "Denied", "Reason": "Conditions not met for authority grant"}
            return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content=bad_resp)
    db_session.close()
    return {"Status": "Granted"}

@app.put("/initiate-recovery")
async def initiate_recovery(failed_server_id: int, request: Request, background_tasks: BackgroundTasks):
    json_data = await request.json()
    
    relinquished_ids = json_data["relinquished_ids"]
    failed_server_id = json_data["server_id"]

    failed_server = db_session.query(Server).filter(Server.id == failed_server_id).first()
    backup_server = db_session.query(Server).filter(Server.id == failed_server.partner_id).first()
    
    failed_server_id = failed_server.id
    backup_server_id = backup_server.id

    if not failed_server.in_failure or not backup_server.in_backup:
        bad_resp = {"Status": "Denied", "Reason": "Conditions not met for recovery"}
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content=bad_resp)

    backup_server_url = f'http://{backup_server.ip_address}:{backup_server.port}/partner?partner_id={failed_server.id}'
    backup_server_resp = requests.request("PUT", backup_server_url)
    if backup_server_resp.ok:
        failed_server_url = f'http://{failed_server.ip_address}:{failed_server.port}/partner?partner_id={backup_server.id}'
        failed_server_resp = requests.request("PUT", failed_server_url)
        if failed_server_resp.ok:
            failed_server.in_failure = False
            backup_server.in_backup = False
            db_session.commit()

    
    db_session.close()
    # The deactivation step of transfer_inventory might be redundant for this case
    # as the failed partner has assumedly already deactivated all of its inventory
    background_tasks.add_task(transfer_inventory, relinquished_ids, backup_server_id, failed_server_id)
    return {"Status": "Queued: Begin Operating"}

def send_server_map(server_id):
    server = db_session.query(Server).filter(Server.id == server_id).first()
    servers = db_session.query(Server).all()
    server_list = []
    for item in servers:
        server_list.append(item.as_dict())
    if server:
        server_url = f'http://{server.ip_address}:{server.port}/servers'
        response = requests.request("PUT", server_url, headers={}, json = server_list)
        if response.ok:
            server.last_updated = datetime.utcnow()
    db_session.commit()
    db_session.close()

def send_inventory(server_id):
    inventory_list = []
    server = db_session.query(Server).filter(Server.id == server_id).first()

    if server.partner_id is not None:
        backup_inventory = db_session.query(Inventory).filter(Inventory.location == server.partner_id).all()
        for item in backup_inventory:
            inventory_list.append(item.as_dict())
            
    inventory = db_session.query(Inventory).filter(Inventory.location == server_id).all()
    for item in inventory:
        inventory_list.append(item.as_dict())

    server_url = f'http://{server.ip_address}:{server.port}/inventory/update'
    response = requests.request("PUT", server_url, headers={}, json = inventory_list)
    if response.ok:
        # db_session.query(Inventory).filter(Inventory.id.in_(reserved_ids)).update({Inventory.location: server_id}, synchronize_session=False)
        server.last_updated = datetime.utcnow()
    db_session.commit()
    db_session.close()

def reserve_orchestrator_inventory(inventory_ids, new_location):
    transaction_id = generate_random_string(TRANSACT_ID_LENGTH)
    # If stored on Orchestrator, lock data first then query for successfully locked data
    db_session.query(Inventory).filter(Inventory.id.in_(inventory_ids), 
                                        Inventory.location == 0, 
                                        Inventory.locked == False).update({Inventory.locked: True, Inventory.last_modified_by: transaction_id}, synchronize_session = False)
    db_session.commit()
    db_session.close()

def request_deactivation(server_id, inventory_ids, write_to_database=False):
    # curr_serv = db_session.query(Server).filter(Server.id == current_location).first()
    deactivated_ids = []
    CHUNK_SIZE = 1000
    curr_serv = db_session.query(Server).filter(Server.id == server_id).first()
    curr_idx = 0
    while curr_idx < len(inventory_ids):
        chunk = inventory_ids[curr_idx:curr_idx+CHUNK_SIZE]
        # sending chunk
        curr_url = f'http://{curr_serv.ip_address}:{curr_serv.port}/inventory/deactivate{"?send_data=True" if write_to_database else ""}'
        response = requests.request("PUT", curr_url, headers={}, json = chunk)
        if response.ok:
            # If the response status code is 200 (OK), parse the response as JSON
            json_data = response.json()
            deactivated_inventory = json_data['deactivated_inventory']

            if write_to_database:
                for item in deactivated_inventory:
                    deactivated_ids.append(item["id"])
                    inv_obj = db_session.query(Inventory).filter(Inventory.id == item['id']).first()
                    # if not inv_obj:
                    #     inv_obj = Inventory()
                    #     db_session.add(inv_obj)
                    for key in item.keys():
                        setattr(inv_obj, key, item[key])
                db_session.commit()
                db_session.close()
            else:
                # If not set to write to database, then just add deactivated ids to
                # return array
                deactivated_ids.append(deactivated_inventory)
        curr_idx += (curr_idx+CHUNK_SIZE)
    return deactivated_ids


def send_and_activate(destination_server, inventory_ids):
    CHUNK_SIZE = 1000
    curr_serv = db_session.query(Server).filter(Server.id == destination_server).first()
    backup_serv = db_session.query(Server).filter(Server.id == curr_serv.partner_id).first()

    CURR_SERV_IP = curr_serv.ip_address
    CURR_SERV_PORT = curr_serv.port

    BACK_SERV_IP = backup_serv.ip_address
    BACK_SERV_PORT = backup_serv.port

    s_current = requests.Session()
    s_backup = requests.Session()
    curr_idx = 0
    # Setting inventory to new worker node location
    db_session.query(Inventory).filter(Inventory.id.in_(inventory_ids), Inventory.location == 0).update({Inventory.location: destination_server}, synchronize_session=False)
    db_session.commit()
    db_session.close()
    while curr_idx < len(inventory_ids):
        backup_response = False
        chunk = inventory_ids[curr_idx:curr_idx+CHUNK_SIZE]
        chunk_query = db_session.query(Inventory).filter(Inventory.id.in_(chunk), Inventory.location == destination_server)
        chunk_data = chunk_query.all()
        chunk_data = [object.as_dict() for object in chunk_data]
        # if partner, send data chunk to backup (partner)
        if backup_serv:
            back_url = f'http://{BACK_SERV_IP}:{BACK_SERV_PORT}/inventory/update'
            upd_response = s_backup.put(back_url, json = chunk_data)
            # upd_response = requests.request("PUT", back_url, headers={}, json = chunk_data)
            backup_response = (upd_response.ok)
        # sending data chunk to primary
        print(f'Sending chunk of length {len(chunk_data)}: with keys [{chunk[0]} ... {chunk[len(chunk)-1]}]')
        curr_url = f'http://{CURR_SERV_IP}:{CURR_SERV_PORT}/inventory/update'
        upd_response = s_current.put(curr_url, json = chunk_data)
        # upd_response = requests.request("PUT", curr_url, headers={}, json = chunk_data)
        
        # If unactivated data successfully received by primary (& backup if applicable), send activate command
        if backup_response:
            curr_url = f'http://{BACK_SERV_IP}:{BACK_SERV_PORT}/inventory/activate'
            active_resp = s_backup.put(curr_url, json = chunk)
            # active_resp = requests.request("PUT", curr_url, headers={}, json = chunk)
        if upd_response.ok:
            curr_url = f'http://{CURR_SERV_IP}:{CURR_SERV_PORT}/inventory/activate'
            active_resp = s_current.put(curr_url, json = chunk)
            # active_resp = requests.request("PUT", curr_url, headers={}, json = chunk)
            # If activate command received, update DB to reflect activation status
            if active_resp.ok:
                chunk_query.update({Inventory.activated: True}, synchronize_session=False)
                db_session.commit()
                db_session.close()
        curr_idx += (curr_idx+CHUNK_SIZE)
    return

def transfer_inventory(inventory_ids, current_location, new_location):
    if current_location != 0:
        # Check if current server has partner
        current_server = db_session.query(Server).filter(Server.id == current_location).first()
        curr_partner_id = current_server.partner_id

        deactivated_ids_partner = inventory_ids
        # If partner, send (non-writing) deactivation request to partner
        if curr_partner_id:
            deactivated_ids_partner = request_deactivation(curr_partner_id, inventory_ids, False)
        
        # Then send (writing) deactivation request to main node
        deactivated_ids_primary = request_deactivation(current_location, inventory_ids, True)

        intersection_result = collections.Counter(deactivated_ids_primary) & collections.Counter(deactivated_ids_partner)
        deactivated_ids = list(intersection_result.elements())
    else:
        db_session.query(Inventory).filter(Inventory.location == current_location, 
                                           Inventory.locked == False).update({Inventory.location: new_location}, synchronize_session=False)
        db_session.commit()
        db_session.close()
        deactivated_ids = inventory_ids
    # Next, check if destination server has partner
    send_and_activate(new_location, deactivated_ids)
    return deactivated_ids

def repair_partnership(relinquished_ids, failed_server_id, backup_server_id):
    failed_server = db_session.query(Server).filter(Server.id == failed_server_id).first()
    backup_server = db_session.query(Server).filter(Server.id == failed_server.partner_id).first()

    # First step is to attempt

@app.put("/reset")
def reset():
    default_inv_dict = {
        Inventory.availability: "Available",
        Inventory.is_dirty: False,
        Inventory.locked: False,
        Inventory.location: 0,
        Inventory.on_backup: False,
        Inventory.transaction_id: None
    }

    default_server_dict = {
        Server.in_failure: False,
        Server.in_backup: False
    }

    db_session.query(Inventory).update(default_inv_dict, synchronize_session = False)
    db_session.query(Server).update(default_server_dict, synchronize_session=False)
    db_session.commit()
    db_session.close()