#!/bin/bash

echo "----- Anti-Hero Distributed System Update -----"
echo "-- Node Types --"
echo "1) Orchestrator"
echo "2) Server"
echo "3) Client"

echo -n "Enter Server Type to Update: "
read x

cd "$WORKDIR"

if [ $x == 1 ]; then
  sudo systemctl stop antihero-orchestrator
  git pull
  sudo systemctl start antihero-orchestrator

elif [ $x == 2 ]; then
  sudo systemctl stop antihero-server
  sudo systemctl stop antihero-serverbg
  git pull
  sudo systemctl start antihero-server
  sudo systemctl start antihero-serverbg

elif [ $x == 3 ]; then
  git pull
  echo "Update complete!"
  echo "Run the command 'source env/bin/activate' to activate the virtualenv"
  echo "Then run 'python client/client.py' to start the client"
else
  echo "Selection is Invalid"
fi