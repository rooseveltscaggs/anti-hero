#!/bin/bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql.service
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'newpassword';"