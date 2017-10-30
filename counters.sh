#!/bin/sh

cd `dirname $0`
python json2mqtt.py --url @counters.conf --mqtt @mqtt.conf --retain \
\
-t /home/sensor/water       '{{response.water | tojson}}'