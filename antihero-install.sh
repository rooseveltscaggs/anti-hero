#!/bin/bash

echo "----- Anti-Hero Distributed System Installer -----"
echo "-- Node Types --"
echo "1) Orchestrator"
echo "2) Server"
echo "3) Client"

echo -n "Enter Server Type to Install: "
read x

if [ $x == 1 ]; then
  echo -n "Automatically initialize inventory? (y/n)"
  read init

USER=$(whoami)
# /Users/rscaggs/git/anti-hero
WORKDIR=$(pwd)
old_text="TEXTDIR"
old_listen_address="#listen_addresses = 'localhost'"
new_listen_address="listen_addresses = '*'"
sudo apt update
sudo apt -y install python3.10
sudo apt -y install postgresql postgresql-contrib
sudo apt -y install python3.10-venv
sudo apt -y install python3-pip
# sudo apt -y install nginx
sudo systemctl start postgresql.service
cd /var/lib/postgresql
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'newpassword';"
sudo ufw allow 5432/tcp
sudo ufw allow 80/tcp
sudo ufw allow 8000/tcp
# echo "Work directory:"
# echo "$WORKDIR"
# sudo cp -rf "$WORKDIR/config/postgresql.conf" /etc/postgresql/14/main/postgresql.conf
sudo sed -i "s|$old_listen_address|$new_listen_address|" "/etc/postgresql/14/main/postgresql.conf"
sudo cp -rf "$WORKDIR/config/pg_hba.conf" /etc/postgresql/14/main/pg_hba.conf
sudo service postgresql restart

cd "$WORKDIR"
sudo rm -rf env/
python3.10 -m venv env
source env/bin/activate
env/bin/pip install -r "$WORKDIR/config/requirements.txt"
deactivate

if [ $x == 1 ]; then
  cd "$WORKDIR/orchestrator"
  sed "s|$old_text|$WORKDIR|" "$WORKDIR/config/antihero-orchestrator.service.template" > "$WORKDIR/config/antihero-orchestrator.service"
  sudo cp -rf "$WORKDIR/config/antihero-orchestrator.service" /etc/systemd/system/antihero-orchestrator.service
  sudo systemctl daemon-reload
  sudo systemctl start antihero-orchestrator
  sudo systemctl enable antihero-orchestrator
  echo "Rebooting services..."
  sleep .8
  sudo systemctl stop antihero-orchestrator
  sudo systemctl start antihero-orchestrator
  # Running inventory initializer...
  if [ $init == "y" ]; then
    cd "$WORKDIR"
    source env/bin/activate
    python3.10 orchestrator/generate_inventory_100.py
    deactivate
  sudo systemctl status antihero-orchestrator
elif [ $x == 2 ]; then
  cd "$WORKDIR/server"
  sed "s|$old_text|$WORKDIR|" "$WORKDIR/config/antihero-server.service.template" > "$WORKDIR/config/antihero-server.service"
  sed "s|$old_text|$WORKDIR|" "$WORKDIR/config/antihero-serverbg.service.template" > "$WORKDIR/config/antihero-serverbg.service"
  sudo cp -rf "$WORKDIR/config/antihero-server.service" /etc/systemd/system/antihero-server.service
  sudo cp -rf "$WORKDIR/config/antihero-serverbg.service" /etc/systemd/system/antihero-serverbg.service
  sudo systemctl daemon-reload
  sudo systemctl start antihero-server
  sudo systemctl enable antihero-server
  sudo systemctl start antihero-serverbg
  sudo systemctl enable antihero-serverbg
  echo "Rebooting services..."
  sleep .8
  sudo systemctl stop antihero-server
  sudo systemctl stop antihero-serverbg
  sudo systemctl start antihero-server
  sudo systemctl start antihero-serverbg
  sudo systemctl status antihero-server
  sudo systemctl status antihero-serverbg



elif [ $x == 3 ]; then
  cd "$WORKDIR"
  echo "Dependency installs complete!"
  echo "Run the command 'source env/bin/activate' to activate the virtualenv"
  echo "Then run 'python client/client.py' to start the client"
else
  echo "Selection is Invalid"
fi