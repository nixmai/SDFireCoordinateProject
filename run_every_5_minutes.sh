#!/bin/bash

while true
do
  echo "Checking fires..."
  python3 fire_check.py
  echo "Sleeping for 5 minutes..."
  sleep 300
done