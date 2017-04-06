#!/bin/sh
cd `dirname $0`
python json2mqtt.py --url @weather.conf --mqtt @mqtt.conf --retain \
\
-t /weather/spb/icon      'http://openweathermap.org/img/w/{{response.weather[0].icon}}.png' \
-t /weather/spb/temp      '{{ "%.1f" | format(response.main.temp) }}' \
-t /weather/spb/pressure  '{{ response.main.pressure }}' \
-t /weather/spb/humidity  '{{ response.main.humidity }}' \
-t /weather/spb/windspeed '{{ response.wind.speed }}' \
-t /weather/spb/sunrise   '{{ response.sys.sunrise | todatetime | datetimeformat("%H:%M") }}' \
-t /weather/spb/sunset    '{{ response.sys.sunset  | todatetime | datetimeformat("%H:%M") }}' \
