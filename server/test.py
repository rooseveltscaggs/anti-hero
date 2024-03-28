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
    if filter:
        query = query.filter(query_filter)
    
    return query.all()


print(readItem(Server, Server.id == 1))