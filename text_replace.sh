#!/bin/bash

WORKDIR=$(pwd)
# WORKDIR="HELLO"
# Define the variable
old_text="TEXTDIR"

# Perform find and replace using sed
# echo "sed "s/$old_text/$WORKDIR/" "config/antihero-orchestrator.service" > output-file"
sed "s|$old_text|$WORKDIR|" "config/antihero-orchestrator.service" > output-file
