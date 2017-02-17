#!/usr/bin/python
# -*- coding: utf-8 -
import requests, json, math
import paho.mqtt.publish as publish
import argparse, logging

url='http://api.openweathermap.org/data/2.5/weather?q=Санкт-Петербург,ru&APPID=b65171098e16aa16531e631d3a27a86f&lang=ru&units=metric'

req = requests.get( 'http://api.openweathermap.org/data/2.5/weather?q=Санкт-Петербург,ru&APPID=b65171098e16aa16531e631d3a27a86f&lang=ru&units=metric' )
data = req.json()
#result = {
# 'temp': math.floor( data['main']['temp']*10 )/10,
# 'icon': 'http://openweathermap.org/img/w/'+data['weather'][0]['icon']+'.png',
# 'pressure': data['main']['pressure'],
# 'humidity': data['main']['humidity'],
# 'windspeed': data['wind']['speed']
#}

parser = argparse.ArgumentParser()
parser.add_argument( "--mqtt", default="localhost:1883" )
parser.add_argument( "--auth" )
parser.add_argument( "-v", action="store_true", default=False, help="Verbose logging", dest="verbose" )
parser.add_argument( "--logfile", help="Logging into file" )
args = parser.parse_args()
logging.basicConfig(format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",  level= logging.DEBUG if args.verbose else logging.INFO, filename=args.logfile )

auth = None if args.auth==None else {'username': args.auth.split(':')[0], 'password':args.auth.split(':')[1] }

publish.single( topic='/weather/spb/icon', payload='http://openweathermap.org/img/w/'+data['weather'][0]['icon']+'.png' , retain=True, auth=auth )
publish.single( topic='/weather/spb/temp', payload=str(math.floor( data['main']['temp']*10 )/10) , retain=True, auth=auth )
publish.single( topic='/weather/spb/pressure', payload=str(data['main']['pressure'] ) , retain=True, auth=auth )
publish.single( topic='/weather/spb/humidity', payload=str(data['main']['humidity'] ) , retain=True, auth=auth )
publish.single( topic='/weather/spb/windspeed', payload=str(data['wind']['speed'] ) , retain=True, auth=auth )