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
  sudo cp -rf /users/"$USER"/anti-hero/antihero-orchestrator.service /etc/systemd/system/antihero.service
  sudo systemctl daemon-reload
  sudo systemctl start antihero-orchestrator
  sudo systemctl enable antihero-orchestrator
elif [ $x == 2 ]; then
  sudo cp -rf /users/"$USER"/anti-hero/antihero-server.service /etc/systemd/system/antihero.service
  sudo cp -rf /users/"$USER"/anti-hero/antihero-serverbg.service /etc/systemd/system/antiherobg.service
  sudo systemctl daemon-reload
  sudo systemctl start antihero-server
  sudo systemctl enable antihero-server
  sudo systemctl start antihero-serverbg
  sudo systemctl enable antihero-serverbg
else
  echo "Selection is Invalid"
fi