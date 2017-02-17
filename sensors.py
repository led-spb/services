#!/usr/bin/python
import logging
import argparse
import time
import paho.mqtt.client as mqtt
import urlparse

try:
  import RPIO as GPIO
except:
  import RPi.GPIO as GPIO
  GPIO.setmode(GPIO.BCM)


class Sensor:
      def __init__(self, data):
          for key,val in data.iteritems():
              setattr(self, key, val)

      def isAlert(self):
          return self.status!=self.normal


def on_mqtt_connect(client, userdata, rc):
    logging.info("MQTT broker connection result: %s", mqtt.connack_string(rc) )

if __name__ == '__main__':
    class LoadFromFile( argparse.Action ):
        def __call__ (self, parser, namespace, values, option_string = None):
           with values as f:
               parser.parse_args(f.read().split(), namespace)

    parser = argparse.ArgumentParser()
    parser.add_argument( "-c", "--config", type=open, action=LoadFromFile, help="Load config from file" )
    parser.add_argument( "-u","--url", default="localhost:1883", type=urlparse.urlparse )
    parser.add_argument( "--auth" )
    parser.add_argument( "--sensor",  nargs="+", help="GPIO sensors, format: name/pin/pull/normal[/timeout=30]", type=str, dest="sensors" )
    parser.add_argument( "-v", action="store_true", default=False, help="Verbose logging", dest="verbose" )
    parser.add_argument( "--logfile", help="Logging into file" )
    args = parser.parse_args()

    # configure logging
    logging.basicConfig(format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",  level= logging.DEBUG if args.verbose else logging.INFO, filename=args.logfile )

    # mqtt broker
    logging.info("Trying connect to MQTT broker at %s:%d" % (args.url.hostname, args.url.port) )

    mqttc = mqtt.Client()
    if args.url.username!=None:
       mqttc.username_pw_set( args.url.username, args.url.password )
    mqttc.on_connect = on_mqtt_connect
    mqttc.connect( args.url.hostname, args.url.port if args.url.port!=None else 1883, 60 )
    mqttc.loop_start()

    # make sensors
    sensors = []
    for s in args.sensors:
        d = s.split("/")
        d.append(30) # append default timeout
        sensors.append( 
           Sensor(
                 {"name": d[0], "pin": int(d[1]), "pull_up": int(d[2]), "normal": int(d[3]), "status":0, "changed":0, "alerted": 0, "timeout": int(d[4]) }
           )
        )

    # Configure sensors
    for sensor in sensors:
        GPIO.setup( sensor.pin,  GPIO.IN, pull_up_down=20+sensor.pull_up )
        sensor.status  = GPIO.input(sensor.pin )
        sensor.changed = time.time()

        logging.info( "Register sensor %s(GPIO%d), state: %d", sensor.name, sensor.pin, sensor.status )
        mqttc.publish( '/home/alarm/sensor/%s' % sensor.name, 1 if sensor.isAlert() else 0, retain=True )

    # Listen for changes
    while True:
        for sensor in sensors:
            value = GPIO.input( sensor.pin )
            if sensor.status!=value:
               time.sleep(0.2)
               value = GPIO.input(sensor.pin )
               now = time.time()

               if sensor.status != value:
                  sensor.status  = value
                  sensor.changed = now

                  logging.info( "Sensor %s(GPIO%d) changed state: %d", sensor.name, sensor.pin, sensor.status )
                  mqttc.publish( '/home/alarm/sensor/%s' % sensor.name, 1 if sensor.isAlert() else 0, retain=True )

        time.sleep(0.1)
