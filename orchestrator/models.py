from sqlalchemy import ForeignKey, func, String, Boolean, Column, Integer, PickleType, DateTime
from database import Base
from sqlalchemy.orm import column_property, relationship
from datetime import datetime, time, timedelta, date

class RegistryEntry(Base):
    __tablename__ = 'registry_entries'
    id = Column(Integer(), primary_key=True, nullable=False)
    registry_name = Column(String(), nullable=False)
    bool_value = Column(Boolean(), nullable=True)
    int_value = Column(Integer(), nullable=True)
    string_value = Column(String(), nullable=True)
    pickle_value = Column(PickleType(), nullable=True)
    datetime_value = Column(DateTime(), nullable=True)

    def as_dict(self):
       return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class ActivityLog(Base):
    __tablename__ = 'activity_log'
    id = Column(Integer(), primary_key=True, nullable=False)
    log_datetime = Column(DateTime(), nullable=True)
    keyword = Column(String(), nullable=True)
    description = Column(String(), nullable=True)

    def as_dict(self):
       return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class Server(Base):
    __tablename__ = 'servers'
    id = Column(Integer(), primary_key=True, nullable=False)
    hostname = Column(String(), nullable=True)
    ip_address = Column(String(), nullable=True)
    port = Column(String(), nullable=True)
    status = Column(String(), nullable=True)
    last_updated = Column(DateTime(), nullable=True)
    partner_id = Column(Integer(), nullable=True)
    in_backup = Column(Boolean(), nullable=True)
    in_failure = Column(Boolean(), nullable=True)
    description = Column(String(), nullable=True)

    def as_dict(self):
       self_dict = {c.name: getattr(self, c.name) for c in self.__table__.columns}
       if self.last_updated is not None:
          self_dict['last_updated'] = self.last_updated.isoformat()
       return self_dict

class Inventory(Base):
    __tablename__ = 'inventory'
    id = Column(Integer(), primary_key=True, nullable=False)
    section = Column(String(), nullable=True)
    row = Column(String(), nullable=True)
    seat = Column(String(), nullable=True)
    desirability = Column(Integer(), nullable=True)
    location = Column(Integer(), nullable=True)
    price = Column(Integer(), nullable=True)
    availability = Column(String(), nullable=True)
    description = Column(String(), nullable=True)
    transaction_id = Column(String(), nullable=True)
    on_backup = Column(Boolean(), nullable=True)
    is_dirty = Column(Boolean(), nullable=True)

    def as_dict(self):
       return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class WorkerTask(Base):
    __tablename__ = 'worker_tasks'
    id = Column(Integer(), primary_key=True, nullable=False)
    task_keyword = Column(String(), nullable=True)
    sender_id = Column(Integer(), nullable=True)
    recipient_id = Column(Integer(), nullable=True)
    ip_address = Column(String(), nullable=True)
    port = Column(String(), nullable=True)
    def as_dict(self):
       return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class Reservation(Base):
    __tablename__ = 'inventory_reservations'
    id = Column(Integer(), primary_key=True, nullable=False)
    server_id = Column(Integer(), nullable=True)
    ip_address = Column(String(), nullable=True)
    inventory_id = Column(Integer(), nullable=True)
    reserve_datetime = Column(DateTime(), nullable=True)
    expiry_time = Column(DateTime(), nullable=True)
    status = Column(String(), nullable=True)
    global_transaction_id = Column(String(), nullable=True)
    forwarded = Column(Boolean(), nullable=True)

    def as_dict(self):
       return {c.name: getattr(self, c.name) for c in self.__table__.columns}
    
