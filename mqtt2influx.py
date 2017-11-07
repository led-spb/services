#!/usr/bin/python
import paho.mqtt.client as paho
import os, sys
import logging
import time
import socket
import json
import signal
import urlparse, argparse
from influxdb import InfluxDBClient

client_id = "MQTT2Infux_%d-%s" % (os.getpid(), socket.getfqdn())

def cleanup(signum, frame):
    #mqttc.publish("/clients/" + client_id, "Offline")
    mqttc.disconnect()
    logging.info("Disconnected from broker; exiting on signal %d", signum)
    sys.exit(signum)


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def on_connect(mosq, userdata, rc):
    logging.info("Connection to broker: %s", paho.connack_string(rc) )
    if rc==0:
      mqttc.publish("/clients/" + client_id, "Online")

      map = userdata['map']
      for topic in map:
          logging.info("Subscribing to topic %s" % topic)
          mqttc.subscribe(topic, 0)


def on_message(mosq, userdata, msg):
    client = userdata['client']
    database = userdata['database']
    map    = userdata['map']

    lines = []
    now = int(time.time())

    for t in map:
        if paho.topic_matches_sub(t, msg.topic):
            (remap) = map[t]
            if remap is None:
                carbonkey = msg.topic.replace('/', '.')
            else:
                carbonkey = remap.replace('/', '.')
            carbonkey=carbonkey.strip('.')

            values={}
            # try to decode payload as json
            try:
              st = json.loads(msg.payload)
              for k in st:
                  if is_number(st[k]):
                     values[k] = float(st[k])
            except:
              # Try to decode payload as number
              try:
                  values['value'] = float(msg.payload)
              except ValueError:
                  logging.debug("Topic %s contains payload [%s] as unknown data format" %  (msg.topic, msg.payload))
                  return

            points=[ {'measurement': carbonkey, 'fields': values } ]
            logging.debug(  "Write to influx %s", json.dumps(points, indent=2) )
            try:
               client.write_points( points, database=database )
            except:
               logging.exception("Error while write data to influxdb")

 
def on_subscribe(mosq, userdata, mid, granted_qos):
    pass


def on_disconnect(mosq, userdata, rc):
    if rc == 0:
        logging.info("Clean disconnection")
    else:
        logging.info("Unexpected disconnect (%s); reconnecting in 5 seconds", paho.connack_string(rc) )
        time.sleep(5)

def parse_host_port(string, default_port):
    d = string.split(":")
    host = d[0]
    port = int(d[1]) if len(d)>1 else default_port 
    return (host,port)
    
def main():
    class LoadFromFile( argparse.Action ):
        def __call__ (self, parser, namespace, values, option_string = None):
           with values as f:
               parser.parse_args(f.read().split(), namespace)

    parser = argparse.ArgumentParser( fromfile_prefix_chars='@' )
    parser.add_argument( "-c", "--config", type=open, action=LoadFromFile, help="Load config from file" )
    parser.add_argument( "--mqtt", default="localhost:1883", type=urlparse.urlparse )
    parser.add_argument( "--database", default="home" )
    parser.add_argument( "--auth" )

    parser.add_argument( "-m", action="append", nargs="*", dest="map" )
    parser.add_argument( "-v", action="store_true", default=False, help="Verbose logging", dest="verbose" )
    parser.add_argument( "--logfile", help="Logging into file" )
    args = parser.parse_args()

    # configure logging
    logging.basicConfig(format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",  level=logging.DEBUG if args.verbose else logging.INFO, filename=args.logfile )

    map = {}
    for item in args.map:
        topic = item[0]
        remap = None if len(item)==1 else item[1]
        map[topic] = (remap)

    influx_client = InfluxDBClient(host='localhost',port=8086, database=args.database)
    try:
      influx_client.create_database(args.database)
    except:
       logging.exception('Create database error')
    userdata = {
        'client' : influx_client,
        'database': args.database,
        'map'    : map,
    }
    influx_client.switch_database(args.database)
    global mqttc

    mqttc = paho.Client(client_id, clean_session=True, userdata=userdata)
    if args.mqtt.username!=None:
       mqttc.username_pw_set(args.mqtt.username, args.mqtt.password )
    mqttc.on_message = on_message
    mqttc.on_connect = on_connect
    mqttc.on_disconnect = on_disconnect
    mqttc.on_subscribe = on_subscribe
    mqttc.connect(args.mqtt.hostname, 1883 if args.mqtt.port==None else args.mqtt.port , 60)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    mqttc.loop_forever()

if __name__ == '__main__':
   main()
