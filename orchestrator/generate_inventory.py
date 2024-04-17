from pydantic import BaseModel
from typing import List, Annotated, Optional
from datetime import datetime, timedelta
from database import db_session, engine
import models
import random
from models import Server, Inventory, Reservation, RegistryEntry

models.Base.metadata.create_all(bind=engine)

print("--- Creating section 100 inventory --")
BASE_PRICE_100 = 450
BASE_DESIRABILITY_100 = 7
# 22 SEATS PER ROW
# ROWS 1 through 22 for each section

# I, J, K: Section, Row, Seat
for i in range(101, 146):
    for j in range(1,22):
        for k in range(1, 22):
            # 78 to 86% are premium
            new_inv = Inventory()
            new_inv.location = 0
            new_inv.is_dirty = False
            new_inv.on_backup = False
            new_inv.write_locked = False
            new_inv.activated = False
            new_inv.availability = "Available"
            new_inv.section = str(i)
            new_inv.row = str(j)
            new_inv.seat = str(k)
            ratio = (i / 146)*100
            # If seat is premium
            if ratio >= 78 and ratio <= 86:
                new_inv.desirability = BASE_DESIRABILITY_100 + 1
                new_inv.price = BASE_PRICE_100 + random.randint(50, 100)
            else:
                new_inv.desirability = BASE_DESIRABILITY_100 + 1
                new_inv.price = BASE_PRICE_100 + random.randint(0, 50)
            db_session.add(new_inv)

print("--- Creating section 200 inventory --")

BASE_PRICE_200 = 300
BASE_DESIRABILITY_200 = 5
# I, J, K: Section, Row, Seat
for i in range(202, 256):
    for j in range(1,22):
        for k in range(1, 22):
            # 78 to 86% are premium
            new_inv = Inventory()
            new_inv.location = 0
            # new_inv.is_dirty = False
            new_inv.on_backup = False
            new_inv.write_locked = False
            new_inv.activated = False
            new_inv.committed = True
            new_inv.availability = "Available"
            new_inv.section = str(i)
            new_inv.row = str(j)
            new_inv.seat = str(k)
            ratio = (i / 256)*100
            # If seat is premium
            if ratio >= 78 and ratio <= 86:
                new_inv.desirability = BASE_DESIRABILITY_200 + 1
                new_inv.price = BASE_PRICE_200 + random.randint(50, 100)
            else:
                new_inv.desirability = BASE_DESIRABILITY_200 + 1
                new_inv.price = BASE_PRICE_200 + random.randint(0, 50)
            db_session.add(new_inv)


print("--- Creating section 300 inventory --")

BASE_PRICE_300 = 100
BASE_DESIRABILITY_300 = 3
# I, J, K: Section, Row, Seat
for i in range(301, 356):
    for j in range(1,22):
        for k in range(1, 22):
            # 78 to 86% are premium
            new_inv = Inventory()
            new_inv.location = 0
            # new_inv.is_dirty = False
            new_inv.on_backup = False
            new_inv.write_locked = False
            new_inv.activated = False
            new_inv.committed = True
            new_inv.availability = "Available"
            new_inv.section = str(i)
            new_inv.row = str(j)
            new_inv.seat = str(k)
            ratio = (i / 356)*100
            # If seat is premium
            if ratio >= 78 and ratio <= 86:
                new_inv.desirability = BASE_DESIRABILITY_300 + 1
                new_inv.price = BASE_PRICE_300 + random.randint(50, 100)
            else:
                new_inv.desirability = BASE_DESIRABILITY_300 + 1
                new_inv.price = BASE_PRICE_300 + random.randint(0, 50)
            db_session.add(new_inv)

db_session.commit()
db_session.close()


FLOOR_SECTIONS = ["A1", "B1", "C1", "D1", "D2", "D3", "D4", "D5", "C2", "B2", "A2", "E1", "E2", "F2", "F3", "F4", "F1"]
VIP_SECTIONS = ["VIPA", "PITA", "PITB", "VIPB", "VIPRISER", "CLUBREN"]