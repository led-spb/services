#!/bin/sh


#!/bin/sh
cd `dirname $0`
python json2mqtt.py --url @counters.conf --mqtt @mqtt.conf --retain \
\
-t /home/water/hot       '{{response.water.hot}}' \
-t /home/water/cold      '{{response.water.cold}}'