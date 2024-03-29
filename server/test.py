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
from models import Server, Inventory, Reservation, RegistryEntry

models.Base.metadata.create_all(bind=engine)

# generate_random_string(Server.id == 2)


def readItem(model, query_filter=None):
    query = db_session.query(model)
    if query_filter:
        query = query.filter(query_filter)
    
    return query.first()

def readItems(model, query_filter=None):
    query = db_session.query(model)
    if query_filter:
        query = query.filter(query_filter)
    
    return query.all()

def acquireLocks(model, ids):
    pass


def writeItem(model, query_filter, values):
    query = db_session.query(model)
    
    # First try and acquire lock item(s)

    # Then update using the values dict

    # Return either the keys of the updated items or the updated objects
    if query_filter:
        query = query.filter(query_filter)
    item = query.first()
    if item:
        for key in values.keys():
            setattr(item, key, values[key])
    db_session.commit()
    
    pass

print(readItem(Server, Server.id == 1))