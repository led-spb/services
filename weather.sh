#!/bin/sh
cd `dirname $0`
python json2mqtt.py --url @weather.conf --mqtt @mqtt.conf --retain \
\
-t /weather/spb '{% set result=response.main -%}{% do result.update({"icon":"http://openweathermap.org/img/w/"+response.weather[0].icon+".png", "windspeed": response.wind.speed }) -%}{{ result | tojson}}'