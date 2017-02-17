#!/usr/bin/python
__author__ = "Jan-Piet Mens"
__copyright__ = "Copyright (C) 2013 by Jan-Piet Mens"

import paho.mqtt.client as paho
import ssl
import os, sys
import logging
import time
import socket
import json
import signal
import argparse

#MQTT_HOST = os.environ.get('MQTT_HOST', 'localhost')
#CARBON_SERVER = os.environ.get('CARBON_SERVER', '127.0.0.1')
#CARBON_PORT = 2003
#MQTT_PORT = 1883
#LOGFORMAT = '%(asctime)-15s %(message)s'
#DEBUG = os.environ.get('DEBUG', False)
#if DEBUG:
#    logging.basicConfig(level=logging.DEBUG, format=LOGFORMAT)
#else:
#    logging.basicConfig(level=logging.INFO, format=LOGFORMAT)


client_id = "MQTT2Graphite_%d-%s" % (os.getpid(), socket.getfqdn())

def cleanup(signum, frame):
    '''Disconnect cleanly on SIGTERM or SIGINT'''
    mqttc.publish("/clients/" + client_id, "Offline")
    mqttc.disconnect()
    logging.info("Disconnected from broker; exiting on signal %d", signum)
    sys.exit(signum)


def is_number(s):
    '''Test whether string contains a number (leading/traling white-space is ok)'''
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

    sock = userdata['sock']
    host = userdata['carbon_server']
    port = userdata['carbon_port']
    lines = []
    now = int(time.time())

    map = userdata['map']
    # Find out how to handle the topic in this message: slurp through
    # our map 
    for t in map:
        if paho.topic_matches_sub(t, msg.topic):
            # print "%s matches MAP(%s) => %s" % (msg.topic, t, map[t])

            # Must we rename the received msg topic into a different
            # name for Carbon? In any case, replace MQTT slashes (/)
            # by Carbon periods (.)
            (type, remap) = map[t]
            if remap is None:
                carbonkey = msg.topic.replace('/', '.')
            else:
                carbonkey = remap.replace('/', '.')
            carbonkey=carbonkey.lstrip('.')

            logging.debug("CARBONKEY is [%s]" % carbonkey)

            if type == 'n':
                '''Number: obtain a float from the payload'''
                try:
                    number = float(msg.payload)
                    lines.append("%s %f %d" % (carbonkey, number, now))
                except ValueError:
                    logging.info("Topic %s contains non-numeric payload [%s]" % 
                            (msg.topic, msg.payload))
                    return

            elif type == 'j':
                '''JSON: try and load the JSON string from payload and use
                   subkeys to pass to Carbon'''
                try:
                    st = json.loads(msg.payload)
                    for k in st:
                        if is_number(st[k]):
                            lines.append("%s.%s %f %d" % (carbonkey, k, float(st[k]), now))
                except:
                    logging.info("Topic %s contains non-JSON payload [%s]" %
                            (msg.topic, msg.payload))
                    return

            else:
                logging.info("Unknown mapping key [%s]", type)
                return

            message = '\n'.join(lines) + '\n'
            logging.debug("%s", message)

            sock.sendto(message, (host, port))
  
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

    parser = argparse.ArgumentParser()
    parser.add_argument( "-c", "--config", type=open, action=LoadFromFile, help="Load config from file" )
    parser.add_argument( "--mqtt", default="localhost:1883" )
    parser.add_argument( "--auth" )
    parser.add_argument( "--carbon", default="127.0.0.1:2003" )
    #parser.add_argument( "--map", type=file, default="map", target="mapfile" )
    parser.add_argument( "-m", action="append", nargs="*", dest="map" )
    parser.add_argument( "-v", action="store_true", default=False, help="Verbose logging", dest="verbose" )
    parser.add_argument( "--logfile", help="Logging into file" )
    args = parser.parse_args()

    # configure logging
    logging.basicConfig(format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",  level=logging.DEBUG if args.verbose else logging.INFO, filename=args.logfile )

    map = {}
    #for line in args.mapfile.readlines():
    #    line = line.rstrip()
    #    if len(line) == 0 or line[0] == '#':
    #        continue
    #    remap = None
    #    try:
    #        type, topic, remap = line.split()
    #    except ValueError:
    #        type, topic = line.split()
    #    map[topic] = (type, remap)
    for item in args.map:
        type = item[0]
        topic = item[1]
        remap = None if len(item)==2 else item[3]
        map[topic] = (type, remap)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except:
        sys.stderr.write("Can't create UDP socket\n")
        sys.exit(1)

    host = parse_host_port(args.carbon,2003)
    userdata = {
        'sock'      : sock,
        'carbon_server' : host[0],
        'carbon_port'   : host[1],
        'map'       : map,
    }
    global mqttc

    mqttc = paho.Client(client_id, clean_session=True, userdata=userdata)
    if args.auth!=None:
       auth = args.auth.split(":")
       mqttc.username_pw_set( auth[0], auth[1] )

    mqttc.on_message = on_message
    mqttc.on_connect = on_connect
    mqttc.on_disconnect = on_disconnect
    mqttc.on_subscribe = on_subscribe

    mqttc.will_set("clients/" + client_id, payload="Adios!", qos=0, retain=False)

    host = parse_host_port(args.mqtt,1883)
    mqttc.connect(host[0], host[1], 60)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    mqttc.loop_forever()

if __name__ == '__main__':
   main()
