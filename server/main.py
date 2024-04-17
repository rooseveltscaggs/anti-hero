from operator import or_
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
import socket
import random
import string
from sqlalchemy import exc
from models import Server, Inventory, Reservation, RegistryEntry

class ForwardedRequest(BaseModel):
    request_time: datetime
    transaction_id: str | None = None
    inventory_ids: List[int]

app = FastAPI()
models.Base.metadata.create_all(bind=engine)

TRANSACT_ID_LENGTH = 10

def common_elements(list1, list2):
    set1 = set(list1)
    set2 = set(list2)
    common_set = set1.intersection(set2)
    common_list = list(common_set)
    return common_list

def list_difference(list1, list2):
    set1 = set(list1)
    set2 = set(list2)
    diff = set1.difference(set2)
    diff_list = list(diff)
    return diff_list


# Local lock (pending commit)
# Make changes
# 

# Prepare local method
# Anti-Hero will attempt to get a local prepare
# If successful, will be returned then changes can be made

# Prepare remote
# Anti-Hero will attempt to send copy of local prepare to backup
# If successful, local prepare will be committed

# Anti-Hero Database Helper Methods

# This function starts a new local commit for specified keys and returns references
# to successfully acquired (locked) keys
def start_local_commit(model, query_filter):
    new_objs = []
    query = db_session.query(model).filter(query_filter).filter(model.activated == True)
    # if query_filter:
        # query = query.filter(query_filter)
    objs = query.all()

    for obj in objs:
        try:
            new_obj = model()
            obj.copy(new_obj)
            db_session.add(new_obj)
            db_session.commit()
            new_objs.append(new_obj)
        except exc.IntegrityError:
            db_session.rollback()
    return new_objs

def read_all_primary(model, query_filters):
    query = db_session.query(model).filter(model.activated == True, model.committed == True)
    for curr_filter in query_filters:
        query = query.filter(curr_filter)
    # if query_filter:
        # query = query.filter(query_filter)
    objs = query.all()
    return objs


# This function is similar to start_local_commit, immediately writes changes
# to the proposed local commit, if keys are successfully (acquired)
def write_to_primary(model, query_filters, values):
    new_objs = []
    query = db_session.query(model).filter(model.activated == True, model.committed == True)
    for curr_filter in query_filters:
        query = query.filter(curr_filter)
    # if query_filter:
        # query = query.filter(query_filter)
    objs = query.all()

    for obj in objs:
        try:
            new_obj = model()
            obj.copy(new_obj)

            for key in values:
                setattr(new_obj, key, values[key])
            
            db_session.add(new_obj)
            db_session.commit()
            new_objs.append(new_obj.as_dict())
        except exc.IntegrityError:
            db_session.rollback()
    return new_objs

# This function is executed on the backup
# Can take dictionary inputs from write_local_commit
def write_to_backup(model, data):
    # Data contains all of the objects in JSON format
    new_objs = []
    # if query_filter:
        # query = query.filter(query_filter)

    for obj in data:
        try:
            new_obj = model()

            for key in obj:
                setattr(new_obj, key, obj[key])
            
            db_session.add(new_obj)
            db_session.commit()
            new_objs.append(new_obj.as_dict())
        except exc.IntegrityError:
            db_session.rollback()
    return new_objs

def send_write_to_backup(model, data):
    route_slug = f'/{model.__qualname__}/prepare'
    # Send data to specific route on backup (if not in backup mode)
    # server_id = retrieve_registry("Server_ID", -1)
    partner_id = retrieve_registry("Partner_ID", 0)
    in_backup = retrieve_registry("In_Backup", False)
    # dirty_ids = ids
    # If stored on Orchestrator
    # Create reservation on Orchestrator

    # Forward Request to Partner (if applicable)
    if not in_backup and partner_id:
        # objs = db_session.query(model).filter(Inventory.location == server_id).all()
        # for item in inventory:
        #     inventory_list.append(item.as_dict())

        # Send forwarded request to partner, if successful commit otherwise rollback
        # Idea: Could send partner transaction ID and it could log that along with the dirty flag
        # In the end, 

        # Background Worker could be in charge of syncing/cleaning up dirty data... it could check DB periodically to see if a certain threshold of dirty data has been reached
        # Would need to capture dirtying/cleanup time (from orignating server, not the partner)...
        partner = db_session.query(Server).filter(Server.id == partner_id).first()
        curr_url = f'http://{partner.ip_address}:{partner.port}' + route_slug
        request_body = {
            "request_time": datetime.utcnow().isoformat(),
            "model": Inventory.__qualname__,
            "data": data
        }
        try:
            response = requests.request("PUT", curr_url, headers={}, json = request_body, timeout=3)
            if response.ok:
                json_data = response.json()

                requested_ids = [obj.id for obj in data]
                accepted_ids = [obj.id for obj in json_data]

                # Removing tentative commits not accepted by backup
                nonaccepted_ids = list_difference(requested_ids, accepted_ids)
                db_session.query(model).filter(model.id.in_(nonaccepted_ids), model.committed == False, model.activated == True).delete(synchronize_session=False)
                db_session.commit()

                return json_data["data"]
        except:
            # rollback changes tenative changes
            uncomitted_ids = [obj.id for obj in data]
            db_session.query(model).filter(model.id.in_(uncomitted_ids), model.committed == False, model.activated == True).delete(synchronize_session=False)
            db_session.commit()
            return []
    else:
        return data

def apply_to_primary(model, query_filters):
    # For all ids with tentatively committed entries, delete the already committed entries
    # and set the tentative ones to committed
    query = db_session.query(model.id).filter(model.activated == True, model.committed == False)
    for curr_filter in query_filters:
        query = query.filter(curr_filter)
    uncommitted_objs = query.filter(model.committed == False).all()
    uncomitted_ids = [obj[0] for obj in uncommitted_objs]

    try:
        db_session.query(model).filter(model.id.in_(uncomitted_ids), model.committed == True, model.activated == True).delete(synchronize_session=False)
        db_session.query(model).filter(model.id.in_(uncomitted_ids), model.committed == False, model.activated == True).update({model.committed: True}, synchronize_session=False)
        db_session.commit()
        return True
    except exc.IntegrityError:
        db_session.rollback()
    
    return False

def apply_to_backup(model, ids):
    return apply_to_primary(model, [Inventory.id.in_(ids)])

def send_apply_to_backup(model, ids):
    # Send apply/commit command to backup (if not in backup mode and has backup)
    route_slug = f'/{model.__qualname__}/apply'
    # Send data to specific route on backup (if not in backup mode)
    # server_id = retrieve_registry("Server_ID", -1)
    partner_id = retrieve_registry("Partner_ID", 0)
    in_backup = retrieve_registry("In_Backup", False)
    # dirty_ids = ids
    # If stored on Orchestrator
    # Create reservation on Orchestrator

    # Forward Request to Partner (if applicable)
    if not in_backup and partner_id:
        # objs = db_session.query(model).filter(Inventory.location == server_id).all()
        # for item in inventory:
        #     inventory_list.append(item.as_dict())

        # Send forwarded request to partner, if successful commit otherwise rollback
        # Idea: Could send partner transaction ID and it could log that along with the dirty flag
        # In the end, 

        # Background Worker could be in charge of syncing/cleaning up dirty data... it could check DB periodically to see if a certain threshold of dirty data has been reached
        # Would need to capture dirtying/cleanup time (from orignating server, not the partner)...
        partner = db_session.query(Server).filter(Server.id == partner_id).first()
        curr_url = f'http://{partner.ip_address}:{partner.port}' + route_slug
        request_body = {
            "request_time": datetime.utcnow().isoformat(),
            "model": model.__qualname__,
            "ids": ids
        }
        try:
            response = requests.request("PUT", curr_url, headers={}, json = request_body, timeout=3)
            if response.ok:
                return True
        except:
            pass
    return False

def invalidate_local_commit():
    # Delete pending commits with specified id
    pass
    

# Basic Helper Methods

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


def update_server_map():
    orc_ip = retrieve_registry("Orchestrator_IP")
    orc_port = retrieve_registry("Orchestrator_Port")
    
    url = f'http://{orc_ip}:{orc_port}/servers'
    response = requests.request("GET", url)
    if response.ok:
        # If the response status code is 200 (OK), parse the response as JSON
        json_data = response.json()
        for server_obj in json_data:
            server = db_session.query(Server).filter(Server.id == server_obj["id"]).first()
            if not server:
                server = Server()
                db_session.add(server)
            server.id = server_obj["id"]
            server.hostname = server_obj["hostname"]
            server.port = server_obj["port"]
            server.description = server_obj["description"]
            server.partner_id = server_obj["partner_id"]
            server.last_updated = server_obj["last_updated"]
            server.status = server_obj["status"]
            db_session.commit()
            db_session.close()
        return json_data
    else:
        return {}

@app.put("/servers")
async def update_all_servers(request: Request):
    json_data = await request.json()
    for server_obj in json_data:
        server = db_session.query(Server).filter(Server.id == server_obj["id"]).first()
        if not server:
            server = Server()
            db_session.add(server)
        server.id = server_obj["id"]
        server.ip_address = server_obj["ip_address"]
        server.hostname = server_obj["hostname"]
        server.port = server_obj["port"]
        server.description = server_obj["description"]
        server.partner_id = server_obj["partner_id"]
        if server_obj["last_updated"] is not None:
            server.last_updated = datetime.fromisoformat(server_obj["last_updated"])
        server.status = server_obj["status"]
        db_session.commit()
    db_session.close()
    return {"status": "Success"}

@app.put("/heartbeat")
def receive_heartbeat():
    request_time = datetime.utcnow()
    status = retrieve_registry("Status")
    if status == 'Disabled':
        raise HTTPException(status_code=503, detail="Service unavailable")
    store_registry("Last_Heartbeat", request_time)
    return {"status": "Success", "received": request_time}

@app.get("/status")
def server_status():
    return {"status": retrieve_registry("Status", None)}

@app.put("/disable")
def server_disable():
    store_registry("Status", "Disabled")
    return {"status": "Disabled"}

@app.put("/enable")
def server_enable():
    store_registry("Status", "Available")
    return {"status": "Available"}

@app.put("/partner")
def pair_servers(partner_id: int):
    update_server_map()
    store_registry("Partner_ID", partner_id)
    store_registry("Last_Heartbeat", None)
    store_registry("Status", "Available")
    store_registry("In_Backup", False)

    partner = db_session.query(Server).filter(Server.id == partner_id).first()
    return partner


@app.put("/orchestrator")
def update_orchestrator(ip_address: str, port: str):
    store_registry("Orchestrator_IP", ip_address)
    store_registry("Orchestrator_Port", port)
    return {"Status": "Updated"}

@app.post("/orchestrator/register")
def register_with_orchestrator(port: Optional[str] = "80"):
    orc_ip = retrieve_registry("Orchestrator_IP")
    orc_port = retrieve_registry("Orchestrator_Port")
    if not orc_ip:
        return {"Error": "Orchestrator location information not specified yet"}

    hostname = socket.gethostname()
    url = f'http://{orc_ip}:{orc_port}/autoregister?hostname={hostname}&port={port}'
    response = requests.request("POST", url, headers={}, params = {})

    if response.ok:
        # If the response status code is 200 (OK), parse the response as JSON
        json_data = response.json()
        print("Autoregister Data:")
        print(json_data)
        store_registry("Server_ID", json_data['id'])
        return json_data
    else:
        return {}

@app.put("/inventory/apply")
async def apply_inventory_commits(request: Request):
    # If not in backup mode, mark data as dirty and respond with success
    in_backup = retrieve_registry("In_Backup")
    status = retrieve_registry("Status")
    if status == "Disabled":
        raise HTTPException(status_code=503, detail="Service unavailable")
    
    json_data = await request.json()
    ids = json_data['ids']
    if not in_backup:
        applied = apply_to_backup(Inventory, ids)
        if applied:
            return {"Status": "Success", "Action": "Commits Applied"}
    # Otherwise, don't make any changes and respond with error
    bad_resp = {"Status": "Failed", "Reason": "Server In Backup Mode"}
    return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content=bad_resp)

@app.put("/inventory/prepare")
async def prepare_inventory_commits(request: Request):
    # If not in backup mode, mark data as dirty and respond with success
    in_backup = retrieve_registry("In_Backup")
    status = retrieve_registry("Status")
    if status == "Disabled":
        raise HTTPException(status_code=503, detail="Service unavailable")
    json_data = await request.json()
    if not in_backup:
        data = json_data["data"]
        data = write_to_backup(Inventory, data)
        return {"Status": "Success", "Action": "Prepare Write", "data": data}
    # Otherwise, don't make any changes and respond with error
    else:
        bad_resp = {"Status": "Failed", "Reason": "Server In Backup Mode"}
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content=bad_resp)

@app.put("/inventory/update")
async def update_all_inventory(request: Request):
    json_data = await request.json()
    print(json_data)
    inv_ids = [obj.id for obj in json_data]
    db_session.query(Inventory).filter(Inventory.id.in_(inv_ids), Inventory.committed == False).delete(synchronize_session=False)
    db_session.commit()
    for item in json_data:
        inv_obj = db_session.query(Inventory).filter(Inventory.id == item['id'], Inventory.committed == True).first()
        if not inv_obj:
            inv_obj = Inventory()
            db_session.add(inv_obj)
        for key in item.keys():
            setattr(inv_obj, key, item[key])
        # Do I need to commit here ?
    db_session.commit() 
    db_session.close()
    print("Inventory updated/created!")
    return {"Status": "Updated"} 

@app.get("/orchestrator/inventory")
def retrieve_orchestrator_inventory():
    orc_ip = retrieve_registry("Orchestrator_IP")
    orc_port = retrieve_registry("Orchestrator_Port")
    
    url = f'http://{orc_ip}:{orc_port}/inventory'
    response = requests.request("GET", url)
    if response.ok:
        # If the response status code is 200 (OK), parse the response as JSON
        json_data = response.json()
        for item in json_data:
            inv_obj = db_session.query(Inventory).filter(Inventory.id == item['id']).first()
            if not inv_obj:
                inv_obj = Inventory(**item)
                db_session.add(inv_obj)
                db_session.commit()
                db_session.close()
            
        return json_data
    else:
        return {}

@app.get("/orchestrator/servers")
def retrieve_orchestrator_servers():
    return update_server_map()

@app.put("/inventory/deactivate")
def deactivate_inventory(ids: List[int], send_data: bool = False, new_location: int = 0):
    # transaction_id = generate_random_string(TRANSACT_ID_LENGTH)
    # server_id = retrieve_registry("Server_ID", None)
    # partner_id = retrieve_registry("Partner_ID", None)
    # reserved_ids = []

    # Locking mechanism is for buy transaction -- so in progress transactions can continue
    # In order to deactivate inventory, inventory must not be write locked or marked dirty on either the primary or the backup
    # In other words, the data must not have been touched by either OR it must have been synchronized after a write
    db_session.query(Inventory).filter(Inventory.id.in_(ids)).update({Inventory.location: new_location, Inventory.activated: False}, synchronize_session = False)
    db_session.commit()
    db_session.close()

    


    # Is it necessary to do last_modified_by? What if server crashes? Should this request be idempotent?
    # ! I think last_modified_by should be removed in this instance... only should be used by the Buy function
    if send_data:
        apply_to_primary(Inventory, [Inventory.id.in_(ids)])
        deactivated_inventory = db_session.query(Inventory).filter(Inventory.location == new_location,
                                       Inventory.id.in_(ids)).all()
    else:
        # Send only the IDs (will this be too big?)
        deactivated_inventory = db_session.query(Inventory.id).filter(Inventory.location == new_location,
                                       Inventory.id.in_(ids)).all()
        deactivated_inventory = [record[0] for record in deactivated_inventory]
        
    # else:
    # # Any AVAILABLE inventory currently on THIS server_id should be changed to location 0 AND have last_modified_by field update to transaction ID
    # # Also deactivate any inventory NOT owned by this server (regardless of status)
    #     db_session.query(Inventory).filter(Inventory.location == server_id, Inventory.availability)
    #     db_session.query(Inventory).filter(or_((Inventory.location == server_id, Inventory.availability == "Available"), (Inventory.location != server_id)), 
    #                                     Inventory.id.in_(ids)).update({ Inventory.location: 0, Inventory.last_modified_by: transaction_id }, synchronize_session=False)
    # db_session.commit()
    # db_session.close()

    # result_query = db_session.query(Inventory.id).filter(Inventory.location == 0, Inventory.id.in_(ids)).all()
    # reserved_ids = [r[0] for r in result_query]

    return {"Status": "Deactivated", "deactivated_inventory": deactivated_inventory}

@app.put("/inventory/activate")
async def activate_inventory(request: Request):
    json_data = await request.json()
    db_session.query(Inventory).filter(Inventory.id.in_(json_data), Inventory.committed == False).delete(synchronize_session=False)
    db_session.query(Inventory).filter(Inventory.id.in_(json_data), Inventory.committed == True).update({Inventory.activated: True}, synchronize_session=False)
    db_session.commit()
    db_session.close()
    return {"Status": "Activated"}


    # inventory_data = json_data["inventory"]
    # ids = json_data["ids"]

    # server_id = retrieve_registry("Server_ID", 0)

    # for all data in inventory_data upsert into database (pre-activated)
    # for item in inventory_data:
    #     inv_obj = db_session.query(Inventory).filter(Inventory.id == item['id']).first()
    #     if not inv_obj:
    #         inv_obj = Inventory()
    #         db_session.add(inv_obj)
    #     for key in item.keys():
    #         setattr(inv_obj, key, item[key])
    # db_session.commit() 
    # db_session.close()

    # for all id numbers included in id, activate them
    # for id in ids:
    #     db_session.query(Inventory).filter(Inventory.id.in_(ids)).update({Inventory.location: server_id}, synchronize_session = False)


    # db_session.commit()
    # db_session.close()

@app.post("/inventory/buy/reserve")
def buy_inventory(ids: List[int], background_tasks: BackgroundTasks):
    status_reg = retrieve_registry("Status")
    if status_reg == "Disabled":
        raise HTTPException(status_code=503, detail="Service unavailable")
    request_time = datetime.utcnow()
    transaction_id = generate_random_string(TRANSACT_ID_LENGTH)
    reserved_ids = []
    server_id = retrieve_registry("Server_ID", -1)
    partner_id = retrieve_registry("Partner_ID", 0)
    in_backup = retrieve_registry("In_Backup", False)
    # If stored on Orchestrator
    # Create reservation on Orchestrator

    # Forward Request to Partner (if applicable)
    if not in_backup and partner_id:
        tentative_data = write_to_primary(Inventory, (Inventory.id.in_(ids), Inventory.availability == 'Available', Inventory.location == server_id), { 'transaction_id': transaction_id, 'availability': 'Reserved' })
        sent_data = send_write_to_backup(Inventory, tentative_data)
        if not sent_data:
            bad_resp = {"Status": "Failed", "Transaction_ID": transaction_id, "Reason": "Unable to reach agreement with partner"}
            return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content=bad_resp)
        
        uncomitted_ids = [obj.id for obj in sent_data]
        commits_applied = apply_to_primary(Inventory, Inventory.id.in_(uncomitted_ids))
        if not commits_applied:
            bad_resp = {"Status": "Failed", "Transaction_ID": transaction_id, "Reason": "Unable to reach agreement with partner"}
            return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content=bad_resp)

        background_tasks.add_task(send_apply_to_backup, Inventory, uncomitted_ids)
    
    else:
        try:
            tentative_data = write_to_primary(Inventory, (Inventory.id.in_(ids), Inventory.availability == 'Available', Inventory.location == server_id), { 'transaction_id': transaction_id, 'availability': 'Reserved' })
            uncomitted_ids = [obj.id for obj in tentative_data]
            commits_applied = apply_to_primary(Inventory, Inventory.id.in_(uncomitted_ids))
            if not commits_applied:
                bad_resp = {"Status": "Failed", "Transaction_ID": transaction_id, "Reason": "Unable to commit to local server"}
                return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content=bad_resp)
        except:
            bad_resp = {"Status": "Failed", "Transaction_ID": transaction_id, "Reason": "Unable to commit to local server"}
            return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content=bad_resp)

    # Might need some type of pausing feature to allow cleanup/synchronization
    # Might want to re-design client/add new experiment where initial transaction ID is return immediately
    # Client then opens new request where they check on the status of their transaction for (10 seconds max)... once they get a successful message back, record request as successful
    
    db_session.commit()
    db_session.close()
    return {"Status": "Success: Awaiting Payment Details", "transaction_id": transaction_id, "reserved_ids": uncomitted_ids}

@app.post("/inventory/buy/payment")
async def submit_payment_details(request: Request, background_tasks: BackgroundTasks):
    status_reg = retrieve_registry("Status")
    if status_reg == "Disabled":
        raise HTTPException(status_code=503, detail="Service unavailable")
    
    server_id = retrieve_registry("Server_ID", -1)
    partner_id = retrieve_registry("Partner_ID", 0)
    in_backup = retrieve_registry("In_Backup", False)

    json_data = await request.json()
    transaction_id = json_data["transaction_id"]
    cc_no = json_data["credit_card_number"]
    if not cc_no or not transaction_id:
        raise HTTPException(status_code=400, detail="Missing payment details or transaction ID")

    if not in_backup and partner_id:
        tentative_data = write_to_primary(Inventory, (Inventory.availability == "Reserved", Inventory.transaction_id == transaction_id, Inventory.location == server_id), {"availability": "Purchased"})
        sent_data = send_write_to_backup(Inventory, tentative_data)
        if not sent_data:
            bad_resp = {"Status": "Failed", "Transaction_ID": transaction_id, "Reason": "Unable to reach agreement with partner"}
            return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content=bad_resp)
        
        uncomitted_ids = [obj.id for obj in sent_data]
        commits_applied = apply_to_primary(Inventory, Inventory.id.in_(uncomitted_ids))
        if not commits_applied:
            bad_resp = {"Status": "Failed", "Transaction_ID": transaction_id, "Reason": "Unable to reach agreement with partner"}
            return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content=bad_resp)
        
        background_tasks.add_task(send_apply_to_backup, Inventory, uncomitted_ids)
    else:
        try:
            tentative_data = write_to_primary(Inventory, (Inventory.availability == "Reserved", Inventory.transaction_id == transaction_id), {"availability": "Purchased"})
            uncomitted_ids = [obj.id for obj in tentative_data]
            commits_applied = apply_to_primary(Inventory, Inventory.id.in_(uncomitted_ids))
            if not commits_applied:
                bad_resp = {"Status": "Failed", "Transaction_ID": transaction_id, "Reason": "Unable to commit to local server"}
                return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content=bad_resp)
        except:
            bad_resp = {"Status": "Failed", "Transaction_ID": transaction_id, "Reason": "Unable to commit to local server"}
            return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content=bad_resp)

    # db_session.query(Inventory).filter(Inventory.transaction_id == transaction_id,).all()
    purchased_tickets = read_all_primary(Inventory, (Inventory.transaction_id == transaction_id,))
    return purchased_tickets

@app.get("/servers")
def get_servers():
    servers = db_session.query(Server).all()
    return servers

@app.post("/servers")
def create_server(host_ip: str, request: Request, hostname: Optional[str] = None, port: Optional[str] = "80"):
    server = Server(hostname=hostname, host_ip=host_ip, port=port)
    db_session.add(server)
    db_session.commit()
    return {"host_ip": host_ip, "hostname": hostname, "server_id": server.id}

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
    server_id = retrieve_registry("Server_ID")
    status = retrieve_registry("Status")
    if status == 'Disabled':
        raise HTTPException(status_code=503, detail="Service unavailable")
    inventory = db_session.query(Inventory).all()
    return inventory

@app.get("/latency/{nil}")
def latency_test(nil: Optional[str]):
    return {"row":"1","section":"101","seat":"1","location":1,"availability":"Available","transaction_id":None,"is_dirty":False,"desirability":8,"id":1,"price":457,"description":None,"on_backup":False}

@app.get("/inventory/{item_id}")
def get_item_status(item_id: int):
    db_session.commit()
    # Check if server is disabled
    server_id = retrieve_registry("Server_ID")
    status = retrieve_registry("Status")
    if status == 'Disabled':
        raise HTTPException(status_code=503, detail="Service unavailable")
    inventory = db_session.query(Inventory).filter(Inventory.id == item_id, 
                                                   Inventory.location == server_id,
                                                   Inventory.activated == True).first()
    if not inventory:
        raise HTTPException(status_code=404, detail="Item not found")
    return inventory


@app.put("/reset")
def reset():
    default_dict = {
        Inventory.availability: "Available",
        Inventory.location: 0,
        Inventory.on_backup: False,
        Inventory.transaction_id: None
    }

    store_registry("Last_Heartbeat", None)
    store_registry("In_Backup", False)
    db_session.query(Inventory).delete(synchronize_session=False)
    db_session.commit()
    db_session.close()