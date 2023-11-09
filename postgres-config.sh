#!/bin/bash
user=$(whoami)
sudo apt update
sudo apt -y install postgresql postgresql-contrib
# sudo apt -y install nginx
sudo systemctl start postgresql.service
cd /var/lib/postgresql
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'newpassword';"
sudo ufw allow 5432/tcp
sudo ufw allow 80/tcp
sudo cp -rf /users/"$USER"/anti-hero/config/postgresql.conf /etc/postgresql/14/main/postgresql.conf
sudo cp -rf /users/"$USER"/anti-hero/config/pg_hba.conf /etc/postgresql/14/main/pg_hba.conf
sudo service postgresql restart

echo "-- Server Types --"
echo "1) Orchestrator"
echo "2) Server"

echo -n "Enter Server Type to Install: "
read x

if [ $x == 1 ]; then
  cd /users/"$USER"/anti-hero/orchestrator
  sudo rm -rf env/
  sudo apt install python3.10-venv
  python -m venv env
  pip install -r requirements.txt
  sudo cp -rf /users/"$USER"/anti-hero/config/antihero-orchestrator.service /etc/systemd/system/antihero-orchestrator.service
  sudo systemctl daemon-reload
  sudo systemctl start antihero-orchestrator
  sudo systemctl enable antihero-orchestrator
  sudo systemctl status antihero-orchestrator
elif [ $x == 2 ]; then
  cd /users/"$USER"/anti-hero/server
  sudo rm -rf env/
  sudo apt install python3.10-venv
  python -m venv env
  pip install -r requirements.txt
  sudo cp -rf /users/"$USER"/anti-hero/config/antihero-server.service /etc/systemd/system/antihero-server.service
  sudo cp -rf /users/"$USER"/anti-hero/config/antihero-serverbg.service /etc/systemd/system/antihero-serverbg.service
  sudo systemctl daemon-reload
  sudo systemctl start antihero-server
  sudo systemctl enable antihero-server
  sudo systemctl start antihero-serverbg
  sudo systemctl enable antihero-serverbg
  sudo systemctl status antihero-server
  sudo systemctl status antihero-serverbg
else
  echo "Selection is Invalid"
fi