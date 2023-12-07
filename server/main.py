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
def update_all_servers(request: Request):
    json_data = request.json()
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

@app.put("/inventory/forward")
def forwarded_request(ids: List[int]):
    # If not in backup mode, mark data as dirty and respond with success
    in_backup = retrieve_registry("In_Backup")
    if not in_backup:
        db_session.query(Inventory).filter(Inventory.id.in_(ids)).update({Inventory.is_dirty: True}, synchronize_session = False)
        db_session.commit()
        db_session.close()
        return {"Status": "Success", "Action": "Marked Dirty", "inventory_ids": ids}
    # Otherwise, don't make any changes and respond with error
    else:
        bad_resp = {"Status": "Failed", "Reason": "Server In Backup Mode"}
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content=bad_resp)

@app.put("/inventory/update")
def update_all_inventory(request: Request):
    json_data = request.json()
    print(json_data)
    for item in json_data:
        inv_obj = db_session.query(Inventory).filter(Inventory.id == item['id']).first()
        if not inv_obj:
            inv_obj = Inventory()
            db_session.add(inv_obj)
        for key in item.keys():
            setattr(inv_obj, key, item[key])
    db_session.commit() 
    db_session.close()
    print("Inventory received and activated!")
    return {"Status": "Activated"} 

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
def deactivate_inventory(ids: List[int], new_location: int):
    request_time = datetime.utcnow()
    server_id = retrieve_registry("Server_ID", None)
    reserved_ids = []
    for inv_id in ids:
        res = Reservation(server_id=new_location, inventory_id=inv_id, reserve_datetime=request_time, expiry_time=request_time+timedelta(minutes=5), status="Requested")
        db_session.add(res)
    db_session.commit()
    db_session.close()
    time.sleep(2)
    # If stored on Orchestrator
    # Create reservation on Orchestrator
    # Wait 5 seconds (resolution period)
    # Begin transfer to new location
    for inv_id in ids:
        existing_res = db_session.query(Reservation).filter(Reservation.inventory_id == inv_id, Reservation.server_id != new_location, Reservation.status != 'Cancelled', Reservation.reserve_datetime <= request_time, Reservation.expiry_time > datetime.utcnow()).first()
        res = db_session.query(Reservation).filter(Reservation.inventory_id == inv_id, Reservation.server_id == new_location, Reservation.reserve_datetime == request_time).first()
        inv = db_session.query(Inventory).filter(Inventory.id == inv_id).first()
        if not existing_res:
            reserved_ids.append(inv_id)
            # This will update to backup (if applicable) once synchronization takes place
            inv.location = 0
            res.status = "Reserved"
        else:
            res.status = "Cancelled"
    db_session.commit()
    return {"Status": "Deactivated", "reserved_ids": reserved_ids}

@app.put("/inventory/activate")
def activate_inventory(ids: List[int]):
    server_id = retrieve_registry("Server_ID", 0)
    db_session.query(Inventory).filter(Inventory.id.in_(ids)).update({Inventory.location: server_id}, synchronize_session = False)
    db_session.commit()
    db_session.close()
    return {"Status": "Activated", "reserved_ids": ids} 

@app.post("/inventory/buy")
def buy_inventory(ids: List[int]):
    request_time = datetime.utcnow()
    transaction_id = generate_random_string(TRANSACT_ID_LENGTH)
    reserved_ids = []
    server_id = retrieve_registry("Server_ID", 0)
    partner_id = retrieve_registry("Partner_ID", 0)
    in_backup = retrieve_registry("In_Backup", False)
    for inv_id in ids:
        res = Reservation(server_id=server_id, inventory_id=inv_id, reserve_datetime=request_time, expiry_time=request_time+timedelta(minutes=5), status="Requested", global_transaction_id=transaction_id)
        db_session.add(res)
    db_session.commit()
    db_session.close()
    time.sleep(2)
    # If stored on Orchestrator
    # Create reservation on Orchestrator
    # Wait 5 seconds (resolution period)
    # Begin transfer to new location
    for inv_id in ids:
        existing_res = db_session.query(Reservation).filter(Reservation.inventory_id == inv_id, Reservation.global_transaction_id != transaction_id, Reservation.status != 'Cancelled', Reservation.reserve_datetime <= request_time, Reservation.expiry_time > datetime.utcnow()).first()
        res = db_session.query(Reservation).filter(Reservation.inventory_id == inv_id, Reservation.global_transaction_id == transaction_id).first()
        inv = db_session.query(Inventory).filter(Inventory.id == inv_id).first()
        if not existing_res:
            reserved_ids.append(inv_id)
            inv.availability = "Purchased"
            res.status = "Reserved"
        else:
            res.status = "Cancelled"
    if not in_backup:
        # Send forwarded request to partner, if successful commit otherwise rollback
        partner = db_session.query(Server).filter(Server.id == partner_id).first()
        curr_url = f'http://{partner.ip_address}:{partner.port}/inventory/forward'
        response = requests.request("PUT", curr_url, headers={}, json = reserved_ids)
        if not response.ok:
            # json_data = response.json()
            # if json_data['Status'] != 'Success':
            db_session.rollback()
            bad_resp = {"Status": "Failed", "Transaction_ID": transaction_id, "Reason": "Unable to reach sync with partner"}
            return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=bad_resp)
    db_session.commit()
    db_session.close()
    return {"Status": "Success", "Transaction_ID": transaction_id, "Inventory": reserved_ids}

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
    inventory = db_session.query(Inventory).filter(Inventory.id == item_id, Inventory.location == server_id).first()
    if not inventory:
        raise HTTPException(status_code=404, detail="Item not found")
    return inventory


@app.put("/reset")
def reset():
    default_dict = {
        Inventory.availability: "Available",
        Inventory.is_dirty: False,
        Inventory.location: 0,
        Inventory.on_backup: False,
        Inventory.transaction_id: None
    }

    db_session.query(Inventory).update(default_dict, synchronize_session = False)
    db_session.commit()
    db_session.close()