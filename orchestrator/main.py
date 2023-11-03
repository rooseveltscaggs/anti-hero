from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from pydantic import BaseModel
from typing import List, Annotated, Optional
from datetime import datetime
import socket
from database import db_session, engine
import models
import requests
import time
from models import Server, Inventory, Reservation, RegistryEntry

app = FastAPI()
models.Base.metadata.create_all(bind=engine)

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
        registry_entry = RegistryEntry(registry_name=key, string_value=value)
        db_session.add(registry_entry)
    else:
        registry_entry.string_value = value
    db_session.commit()
    db_session.close()
    return value

def retrieve_registry(key, default=None):
    registry_entry = db_session.query(RegistryEntry).filter(RegistryEntry.registry_name == key).first()
    if registry_entry:
        return registry_entry.string_value
    else:
        return default


@app.post("/autoregister")
def auto_register(request: Request, hostname: Optional[str] = None, port: Optional[str] = "80"):
    host_ip = request.client.host
    existing_server = db_session.query(Server).filter(Server.hostname==hostname, Server.ip_address==host_ip, Server.port==port).first()
    if existing_server:
        return existing_server
    else:
        server = Server(hostname=hostname, ip_address=host_ip, port=port)
        db_session.add(server)
        db_session.commit()
        # return {"host_ip": host_ip, "hostname": hostname, "server_id": server.id}
        return server

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
    inventory = db_session.query(Inventory).all()
    return inventory

@app.get("/inventory/{item_id}")
def get_item_status(item_id: int):
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
        inventory_ids = db_session.query(Inventory.id).filter(Inventory.location == location).all()
        background_tasks.add_task(transfer_inventory, inventory_ids, location, destination)
    
    return {"Status": "Queued"}

def transfer_inventory(inventory_ids, current_location, new_location):
    request_time = datetime.utcnow()
    reserved_ids = []
    if current_location == 0:
        for inv_id in inventory_ids:
            res = Reservation(server_id=new_location, inventory_id=inv_id, reserve_datetime=request_time, expiry_time=request_time+datetime.timedelta(minutes=5), status="Requested")
            db_session.add(res)
        db_session.commit()
        db_session.close()
        time.sleep(5)
        # If stored on Orchestrator
        # Create reservation on Orchestrator
        # Wait 5 seconds (resolution period)
        # Begin transfer to new location
        for inv_id in inventory_ids:
            existing_res = db_session.query(Reservation).filter(Reservation.inventory_id == inv_id, Reservation.server_id != new_location, Reservation.status != 'Cancelled', Reservation.reserve_datetime <= request_time, Reservation.expiry_time > datetime.utcnow()).first()
            res = db_session.query(Reservation).filter(Reservation.inventory_id == inv_id, Reservation.server_id == new_location, Reservation.reserve_datetime == request_time).first()
            inv = db_session.query(Inventory).filter(Inventory.id == inv_id).first()
            if not existing_res:
                reserved_ids.append(inv_id)
                inv.location = new_location
                res.status = "Reserved"
            else:
                res.status = "Cancelled"
        db_session.commit()
            
    else:
        curr_serv = db_session.query(Server).filter(Server.id == current_location).first()
        if curr_serv:
            curr_url = f'http://{curr_serv.ip_address}:{curr_serv.port}/inventory/deactivate'
            payload = {
                "q" : inventory_ids
            }
            response = requests.request("PUT", curr_url, headers={}, params = payload)

            if response.ok:
                # If the response status code is 200 (OK), parse the response as JSON
                json_data = response.json()
                reserved_ids = json_data['reserved_ids']
        
    dest_serv = db_session.query(Server).filter(Server.id == new_location).first()
    if dest_serv:
        # request inventory from current server
        # api route: /inventory/lock

        curr_url = f'http://{dest_serv.ip_address}:{dest_serv.port}/inventory/activate'
        payload = {
            "q" : inventory_ids
        }
        response = requests.request("PUT", curr_url, headers={}, params = payload)

        if response.ok:
            # If the response status code is 200 (OK), parse the response as JSON
            json_data = response.json()
    db_session.close()
    return response