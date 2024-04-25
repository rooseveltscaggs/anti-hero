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
import random
from models import Server, Inventory, Reservation, RegistryEntry

app = FastAPI()
models.Base.metadata.create_all(bind=engine)

TRANSACT_ID_LENGTH = 10

def list_difference(list1, list2):
    set1 = set(list1)
    set2 = set(list2)
    diff = set1.difference(set2)
    diff_list = list(diff)
    return diff_list

def common_elements(list1, list2):
    set1 = set(list1)
    set2 = set(list2)
    common_set = set1.intersection(set2)
    common_list = list(common_set)
    return common_list

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
            default = registry_entry.int_value
        
        if registry_entry.string_value is not None:
            default = registry_entry.string_value
        
        if registry_entry.bool_value is not None:
            default = registry_entry.bool_value
        
        if registry_entry.datetime_value is not None:
            default = registry_entry.datetime_value
    
    db_session.close() 
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
def start_pair_servers(server1_id: int, server2_id: int, background_tasks: BackgroundTasks):
    server1 = db_session.query(Server).filter(Server.id == server1_id).first()
    server2 = db_session.query(Server).filter(Server.id == server2_id).first()
    if server1 and server2:
        if server1.partner_id or server2.partner_id:
            return {"Status": "Server(s) already paired"} 

        # Deactivate all data on both nodes (stored locally)
        server1_keys = db_session.query(Inventory.id).filter(Inventory.location == server1_id).all()
        server2_keys = db_session.query(Inventory.id).filter(Inventory.location == server2_id).all()
        server1_keys = [obj[0] for obj in server1_keys]
        server2_keys = [obj[0] for obj in server2_keys]

        server1_keys = request_deactivation(server1_id, server1_keys, True)
        server2_keys = request_deactivation(server2_id, server2_keys, True)

        # Pair nodes together now that inventory is deactivated
        server1 = db_session.query(Server).filter(Server.id == server1_id).first()
        server2 = db_session.query(Server).filter(Server.id == server2_id).first()
        server1_url = f'http://{server1.ip_address}:{server1.port}/partner?partner_id={server2_id}'
        response = requests.request("PUT", server1_url)
        if response.ok:
            server2_url = f'http://{server2.ip_address}:{server2.port}/partner?partner_id={server1_id}'
            response = requests.request("PUT", server2_url)
            if response.ok:
                print("Updating partners")
                server1.partner_id = int(server2_id)
                server2.partner_id = int(server1_id)
        print("Committing to database")
        db_session.commit()
        db_session.close()

        # transfer_inventory(server1_keys, 0, server1_id)
        # transfer_inventory(server2_keys, 0, server2_id)

        background_tasks.add_task(transfer_inventory, server1_keys, 0, server1_id)
        background_tasks.add_task(transfer_inventory, server2_keys, 0, server2_id)
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
    print(f'Received transfer request array of length {len(ids)} with ids {ids[0]} ... {ids[len(ids)-1]}')
    locations = db_session.query(Inventory.location).filter(Inventory.id.in_(ids)).group_by(Inventory.location).all()
    for location in locations:
        inventory_ids = db_session.query(Inventory.id).filter(Inventory.location == location[0], Inventory.id.in_(ids)).all()
        inventory_ids = [record[0] for record in inventory_ids]
        print("-- Inventory Transfer -- ")
        # print(inventory_ids)
        print(f'Inititating transfer of array with length {len(inventory_ids)} with ids {inventory_ids[0]} ... {inventory_ids[len(inventory_ids)-1]}')
        background_tasks.add_task(transfer_inventory, inventory_ids, location[0], destination)
    db_session.close()
    return {"Status": "Queued"}

@app.put("/failure")
def report_failure(failed_server_id: int, backup_server_id: int):
    print("Failure reported!")
    failed_server = db_session.query(Server).filter(Server.id == failed_server_id).first()
    backup_server = db_session.query(Server).filter(Server.id == backup_server_id).first()
    db_session.refresh(failed_server)
    db_session.refresh(backup_server)


    if failed_server and backup_server:

        # if failed_server.partner_id == backup_server_id:
        #     return {"Status": "Granted"}
        # If reporting server was already promoted/not in a partnership  OR it has a partnership AND the other node matches
        if not backup_server.partner_id or (backup_server.partner_id and failed_server.partner_id == backup_server_id):
            print("Granting authority...")
            # failed_server.in_failure = True
            # backup_server.in_backup = True

            # Updating hashmap to reflect backup server inheriting failed node's keys
            # Only if this is the first time the node has requested authority
            if backup_server.partner_id:
                db_session.query(Inventory).filter(Inventory.location == failed_server_id, Inventory.write_locked != True).update({ Inventory.location: backup_server_id }, synchronize_session=False)

            # Promoting/reverting (reporting) backup server to solo mode
            backup_server.partner_id = None

            db_session.commit()
            db_session.close()
            return {"Status": "Granted"}
        
        
        
        
    print("Denying authority...")
    bad_resp = {"Status": "Denied", "Reason": "Conditions not met for authority grant"}
    db_session.close()
    return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content=bad_resp)

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
    # ! Not paginated, will be a problem for big transfers
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


def post_recovery(relinquished_ids, deactivated_ids, unchanged_deactivated_ids, src_server_id, dest_server_id):
    # Pair servers
    print("post_recovery: Re-Pairing Servers")
    pair_servers(dest_server_id, src_server_id)


    # Optimized reactivation: Reactivate keys that haven't been changed since the timeout
    print("post_recovery: Re-activating unchanged inventory (Optimized)")
    unchanged_relinquished_ids = common_elements(unchanged_deactivated_ids, relinquished_ids)
    unchanged_remaining_ids = list_difference(deactivated_ids, unchanged_relinquished_ids)
    print("Length of unchanged_relinquished_ids: " + str(len(unchanged_relinquished_ids)))
    print("Length of unchanged_remaining_ids: " + str(len(unchanged_remaining_ids)))

    print("post_recovery: Resynchronizing conflicting inventory")
    reactivate_clean_data(src_server_id, dest_server_id, dest_server_id, unchanged_relinquished_ids)
    reactivate_clean_data(src_server_id, dest_server_id, src_server_id, unchanged_remaining_ids)
    remaining_ids = list_difference(deactivated_ids, unchanged_deactivated_ids)
    remaining_relinquished_ids = list_difference(relinquished_ids, unchanged_relinquished_ids)
    print("Length of remaining_ids: " + str(len(remaining_ids)))
    print("Length of remaining_relinquished_ids: " + str(len(remaining_relinquished_ids)))

    # Sync inventory
    sync_inventory(remaining_relinquished_ids, remaining_ids, src_server_id, dest_server_id)


def pair_servers(failed_server_id, backup_server_id):
    failed_server = db_session.query(Server).filter(Server.id == failed_server_id).first()
    backup_server = db_session.query(Server).filter(Server.id == backup_server_id).first()

    # Pair servers together
    backup_server_url = f'http://{backup_server.ip_address}:{backup_server.port}/partner?partner_id={failed_server_id}'
    backup_server_resp = requests.request("PUT", backup_server_url)
    if backup_server_resp.ok:
        failed_server_url = f'http://{failed_server.ip_address}:{failed_server.port}/partner?partner_id={backup_server_id}'
        failed_server_resp = requests.request("PUT", failed_server_url)
        if failed_server_resp.ok:
            failed_server.partner_id = backup_server_id
            backup_server.partner_id = failed_server_id
            db_session.commit()
            db_session.close()
            

# Relinquished IDs are the keys the previously failed node is requesting to regain
# Deactivated IDs are all the keys successfully (deactivated)
# The remaining deactivated keys are ones to be assigned to the src_server
def reactivate_clean_data(src_server_id, dest_server_id, new_location, unchanged_deactivated_data=None):
    if not unchanged_deactivated_data:
        return None
    # Node that didn't fail
    src_server = db_session.query(Server).filter(Server.id == src_server_id).first()
    # timeout_reported = src_server.timeout_reported

    # Node that previously failed
    dest_server = db_session.query(Server).filter(Server.id == dest_server_id).first()
    
    
    CHUNK_SIZE = 1000

    curr_idx = 0
    while curr_idx < len(unchanged_deactivated_data):
        chunk = unchanged_deactivated_data[curr_idx:curr_idx+CHUNK_SIZE]
        src_url = f'http://{src_server.ip_address}:{src_server.port}/inventory/activate?new_location={new_location}'
        dest_url = f'http://{dest_server.ip_address}:{dest_server.port}/inventory/activate?new_location={new_location}'
        # active_resp = s_backup.put(curr_url, json = chunk)
        src_resp = requests.request("PUT", src_url, headers={}, json = chunk)
        dest_resp = requests.request("PUT", dest_url, headers={}, json = chunk)
        curr_idx = (curr_idx+CHUNK_SIZE)

# Relinquished IDs are the keys the previously failed node is requesting to regain
# Deactivated IDs are all the keys successfully (deactivated)
# The remaining deactivated keys are ones to be assigned to the src_server
def sync_inventory(relinquished_ids, deactivated_ids, src_server_id, dest_server_id):
    print("sync_inventory - relinquished_ids: " + str(relinquished_ids))
    print("sync_inventory - deactivated_ids: " + str(deactivated_ids))
    print("sync_inventory - src_server_id: " + str(src_server_id))
    print("sync_inventory - dest_server_id: " + str(dest_server_id))

    # Node that didn't fail
    # src_server = db_session.query(Server).filter(Server.id == src_server_id).first()

    # Node that previously failed
    # dest_server = db_session.query(Server).filter(Server.id == dest_server_id).first()
    
    CHUNK_SIZE = 1000

    curr_idx = 0
    while curr_idx < len(relinquished_ids):
        chunk = relinquished_ids[curr_idx:curr_idx+CHUNK_SIZE]
        deactivated_ids_chunk = request_deactivation(src_server_id, chunk, True)
        send_and_activate(dest_server_id, deactivated_ids_chunk)

        curr_idx = (curr_idx+CHUNK_SIZE)

    remaining_ids = list_difference(deactivated_ids, relinquished_ids)

    print("sync_inventory - remaining_ids: " + str(remaining_ids))
    curr_idx = 0
    while curr_idx < len(remaining_ids):
        chunk = remaining_ids[curr_idx:curr_idx+CHUNK_SIZE]
        print("Requesting deactivation of chunk to be sent to backup node")
        deactivated_ids_chunk = request_deactivation(src_server_id, chunk, True)
        print("sync_inventory - deactivated_ids_chunk: " + str(deactivated_ids_chunk))
        send_and_activate(src_server_id, deactivated_ids_chunk)

        curr_idx = (curr_idx+CHUNK_SIZE)
    db_session.close()


def reserve_orchestrator_inventory(inventory_ids, new_location):
    transaction_id = generate_random_string(TRANSACT_ID_LENGTH)
    # If stored on Orchestrator, lock data first then query for successfully locked data
    db_session.query(Inventory).filter(Inventory.id.in_(inventory_ids), 
                                        Inventory.location == 0, 
                                        Inventory.write_locked != True).update({Inventory.write_locked: True, Inventory.last_modified_by: transaction_id}, synchronize_session = False)
    db_session.commit()
    db_session.close()

def request_deactivation_detailed(server_id, inventory_ids, new_location=0):
    # curr_serv = db_session.query(Server).filter(Server.id == current_location).first()
    curr_serv = db_session.query(Server).filter(Server.id == server_id).first()
    CURR_SERV_IP = curr_serv.ip_address
    CURR_SERV_PORT = curr_serv.port
    curr_url = f'http://{CURR_SERV_IP}:{CURR_SERV_PORT}/inventory/deactivate?new_location={new_location}'
    response = requests.request("PUT", curr_url, headers={}, json = inventory_ids)
    if response.ok:
        # If the response status code is 200 (OK), parse the response as JSON
        json_data = response.json()
        return json_data
    return None

def request_deactivation(server_id, inventory_ids, write_to_database=False, new_location=0):
    # curr_serv = db_session.query(Server).filter(Server.id == current_location).first()
    deactivated_ids = []
    CHUNK_SIZE = 1000
    curr_serv = db_session.query(Server).filter(Server.id == server_id).first()
    CURR_SERV_IP = curr_serv.ip_address
    CURR_SERV_PORT = curr_serv.port
    curr_idx = 0
    while curr_idx < len(inventory_ids):
        chunk = inventory_ids[curr_idx:curr_idx+CHUNK_SIZE]
        # sending chunk
        curr_url = f'http://{CURR_SERV_IP}:{CURR_SERV_PORT}/inventory/deactivate?new_location={new_location}{"&send_data=True" if write_to_database else ""}'
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
                    inv_obj.location = 0
                db_session.commit()
                db_session.close()
            else:
                # If not set to write to database, then just add deactivated ids to
                # return array
                deactivated_ids += deactivated_inventory
        curr_idx = (curr_idx+CHUNK_SIZE)
    db_session.close()
    return deactivated_ids


def send_and_activate(destination_server_id, inventory_ids):
    CHUNK_SIZE = 1000
    BACK_SERV_IP = ""
    BACK_SERV_PORT = ""
    curr_serv = db_session.query(Server).filter(Server.id == destination_server_id).first()
    backup_serv = db_session.query(Server).filter(Server.id == curr_serv.partner_id).first()

    CURR_SERV_IP = curr_serv.ip_address
    CURR_SERV_PORT = curr_serv.port
    s_backup = None

    # This is None if curr_serv has no partner
    if backup_serv:
        BACK_SERV_IP = backup_serv.ip_address
        BACK_SERV_PORT = backup_serv.port

    # s_backup = requests.Session()
    # s_current = requests.Session()
    curr_idx = 0
    # Setting inventory to new worker node location
    db_session.query(Inventory).filter(Inventory.id.in_(inventory_ids), Inventory.location == 0).update({Inventory.location: destination_server_id}, synchronize_session=False)
    db_session.commit()
    db_session.close()
    while curr_idx < len(inventory_ids):
        backup_response = False
        chunk = inventory_ids[curr_idx:curr_idx+CHUNK_SIZE]
        chunk_query = db_session.query(Inventory).filter(Inventory.id.in_(chunk), Inventory.location == destination_server_id)
        chunk_data = chunk_query.all()
        chunk_data = [object.as_dict() for object in chunk_data]
        # if partner, send data chunk to backup (partner)
        # Backup_serv is not transient (db close is above this)
        if BACK_SERV_IP:
            back_url = f'http://{BACK_SERV_IP}:{BACK_SERV_PORT}/inventory/update'
            # upd_response = s_backup.put(back_url, json = chunk_data)
            upd_response = requests.request("PUT", back_url, headers={}, json = chunk_data)
            backup_response = (upd_response.ok)
        # sending data chunk to primary
        print(f'Sending chunk of length {len(chunk_data)}: with keys [{chunk[0]} ... {chunk[len(chunk)-1]}]')
        curr_url = f'http://{CURR_SERV_IP}:{CURR_SERV_PORT}/inventory/update'
        # upd_response = s_current.put(curr_url, json = chunk_data)
        upd_response = requests.request("PUT", curr_url, headers={}, json = chunk_data)
        
        # If unactivated data successfully received by primary (& backup if applicable), send activate command
        if backup_response:
            curr_url = f'http://{BACK_SERV_IP}:{BACK_SERV_PORT}/inventory/activate'
            # active_resp = s_backup.put(curr_url, json = chunk)
            active_resp = requests.request("PUT", curr_url, headers={}, json = chunk)
        if upd_response.ok:
            curr_url = f'http://{CURR_SERV_IP}:{CURR_SERV_PORT}/inventory/activate'
            # active_resp = s_current.put(curr_url, json = chunk)
            active_resp = requests.request("PUT", curr_url, headers={}, json = chunk)
            # If activate command received, update DB to reflect activation status
            if active_resp.ok:
                chunk_query.update({Inventory.activated: True}, synchronize_session=False)
                db_session.commit()
                db_session.close()
        curr_idx = (curr_idx+CHUNK_SIZE)
    db_session.close()
    return

def transfer_inventory(inventory_ids, current_location, new_location):
    if current_location != 0:
        # Check if current server has partner
        current_server = db_session.query(Server).filter(Server.id == current_location).first()
        curr_partner_id = current_server.partner_id
        db_session.close()

        deactivated_ids_partner = inventory_ids
        print("Requesting deactivation of inventory...")
        # If partner, send (non-writing) deactivation request to partner
        if curr_partner_id:
            deactivated_ids_partner = request_deactivation(curr_partner_id, inventory_ids, False)
        
        # Then send (writing) deactivation request to main node
        deactivated_ids_primary = request_deactivation(current_location, inventory_ids, True)

        deactivated_ids = common_elements(deactivated_ids_partner, deactivated_ids_primary)
    else:
        # db_session.query(Inventory).filter(Inventory.id.in_(inventory_ids),
        #                                    Inventory.location == current_location, 
        #                                    Inventory.write_locked != True).update({Inventory.location: new_location}, synchronize_session=False)
        # db_session.commit()
        orc_keys = db_session.query(Inventory.id).filter(Inventory.id.in_(inventory_ids), Inventory.location == current_location).all()
        deactivated_ids = [obj[0] for obj in orc_keys]
        db_session.close()
    # Next, check if destination server has partner
    print("Sending and activating inventory...")
    send_and_activate(new_location, deactivated_ids)
    return deactivated_ids

# def repair_partnership(relinquished_ids, failed_server_id, backup_server_id):
#     failed_server = db_session.query(Server).filter(Server.id == failed_server_id).first()
#     backup_server = db_session.query(Server).filter(Server.id == failed_server.partner_id).first()

#     # First step is to attempt

@app.put("/initiate-recovery")
async def initiate_recovery(request: Request, background_tasks: BackgroundTasks):
    # Receiving this request means the failed node is acknowledging
    # its failure and has already relinquished its old local data
    # Therefore, we can now safely mark it as being in Solo Mode
    print("Recovery request received...")
    json_data = await request.json()
    
    relinquished_ids = json_data["relinquished_ids"]
    print("Relinquished keys from failed server: " + str(relinquished_ids))
    failed_server_id = json_data["server_id"]

    failed_server = db_session.query(Server).filter(Server.id == failed_server_id).first()
    backup_server = db_session.query(Server).filter(Server.id == failed_server.partner_id).first()

    failed_server_id = failed_server.id
    backup_server_id = backup_server.id

    # Set previously failed node to Solo Mode
    failed_server.partner_id = None
    db_session.commit()

    db_session.refresh(failed_server)
    db_session.refresh(backup_server)

    # If previous partner has already been re-matched, allow previously failed node to simply operate in Solo Mode
    if backup_server.partner_id:
        # Officially return failed_server to solo mode
        # failed_server.partner_id = None
        # db_session.commit()
        # db_session.close()
        return {"Status": "Previous Partner Unavailable: Begin Operating in Solo Mode"}

    
    # If previous partner is in Solo Mode (aka can be re-paired with failed node)

    # (Silently) deactivate data on previous partner
    backup_records = db_session.query(Inventory.id).filter(Inventory.location == backup_server_id).all()
    backup_keys = [obj[0] for obj in backup_records]
    print("Requesting deactivation for keys: " + str(backup_keys))
    deactivation_data = request_deactivation_detailed(backup_server_id, backup_keys)
    unchanged_deactivated_data = deactivation_data["unchanged_deactivated_data"]
    deactivated_keys = deactivation_data["deactivated_inventory"]
    print("Silent deactivated keys: " + str(deactivated_keys))


    # Temporarily mark successfully deactivated keys as belonging to Orchestrator (location = 0)
    # db_session.query(Inventory).filter(Inventory.id.in_(deactivated_keys)).update({ Inventory.location: 0 }, synchronize_session=False)
    # db_session.commit()


    # # Reopening DB connection closed by request_deactivation
    # failed_server = db_session.query(Server).filter(Server.id == failed_server_id).first()
    # backup_server = db_session.query(Server).filter(Server.id == backup_server_id).first()

    # # Pair servers together
    # backup_server_url = f'http://{backup_server.ip_address}:{backup_server.port}/partner?partner_id={failed_server_id}'
    # backup_server_resp = requests.request("PUT", backup_server_url)
    # if backup_server_resp.ok:
    #     failed_server_url = f'http://{failed_server.ip_address}:{failed_server.port}/partner?partner_id={backup_server_id}'
    #     failed_server_resp = requests.request("PUT", failed_server_url)
    #     if failed_server_resp.ok:
    #         failed_server.partner_id = backup_server_id
    #         backup_server.partner_id = failed_server_id
    #         db_session.commit()
    #         db_session.close()

    
    # The deactivation step of transfer_inventory might be redundant for this case
    # as the failed partner has assumedly already deactivated all of its inventory

    # sync_inventory(relinquished_ids, deactivated_keys, backup_server_id, failed_server_id)
    background_tasks.add_task(post_recovery, relinquished_ids, deactivated_keys, unchanged_deactivated_data, backup_server_id, failed_server_id)
    # background_tasks.add_task(sync_inventory, relinquished_ids, deactivated_keys, backup_server_id, failed_server_id)
    return {"Status": "Queued: Begin Operating"}

@app.put("/reset")
def reset():
    default_inv_dict = {
        Inventory.availability: "Available",
        Inventory.write_locked: False,
        Inventory.location: 0,
        Inventory.on_backup: False,
        Inventory.transaction_id: None
    }

    default_server_dict = {
        Server.in_failure: False,
        Server.in_backup: False,
        Server.partner_id: None
    }

    db_session.query(Inventory).update(default_inv_dict, synchronize_session = False)
    db_session.query(Server).update(default_server_dict, synchronize_session=False)
    db_session.commit()
    db_session.close()