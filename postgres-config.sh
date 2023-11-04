#!/bin/bash
user=$(whoami)
sudo apt update
sudo apt -y install postgresql postgresql-contrib
sudo systemctl start postgresql.service
cd /var/lib/postgresql
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'newpassword';"
sudo ufw allow 5432/tcp
sudo cp -rf /home/"$USER"/anti-hero/postgresql.conf /etc/postgresql/14/main/postgresql.conf
sudo cp -rf /home/"$USER"/anti-hero/pg_hba.conf /etc/postgresql/14/main/pg_hba.conf
sudo service postgresql restart