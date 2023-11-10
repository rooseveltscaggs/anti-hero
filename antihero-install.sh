#!/bin/bash
USER=$(whoami)
# /Users/rscaggs/git/anti-hero
WORKDIR=$(pwd)
sudo apt update
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
echo "Work directory:"
echo "$WORKDIR"
sudo cp -rf "$WORKDIR/config/postgresql.conf" /etc/postgresql/14/main/postgresql.conf
sudo cp -rf "$WORKDIR/config/pg_hba.conf" /etc/postgresql/14/main/pg_hba.conf
sudo service postgresql restart

echo "-- Server Types --"
echo "1) Orchestrator"
echo "2) Server"

echo -n "Enter Server Type to Install: "
read x

if [ $x == 1 ]; then
  cd "$WORKDIR/orchestrator"
  # sudo rm -rf env/
  # python3 -m venv env
  # source env/bin/activate
  pip install -r requirements.txt
  sudo cp -rf "$WORKDIR/config/antihero-orchestrator.service" /etc/systemd/system/antihero-orchestrator.service
  sudo systemctl daemon-reload
  sudo systemctl start antihero-orchestrator
  sudo systemctl enable antihero-orchestrator
  sudo systemctl status antihero-orchestrator
elif [ $x == 2 ]; then
  cd "$WORKDIR/server"
  # sudo rm -rf env/
  # python3 -m venv env
  # source env/bin/activate
  pip install -r requirements.txt
  sudo cp -rf "$WORKDIR/config/antihero-server.service" /etc/systemd/system/antihero-server.service
  sudo cp -rf "$WORKDIR/config/antihero-serverbg.service" /etc/systemd/system/antihero-serverbg.service
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