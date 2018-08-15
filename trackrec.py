#!/usr/bin/python

import logging
import argparse
import urlparse
import paho.mqtt.client as mqtt
import json, zlib
import os.path
import gpxpy.gpx
from gpxpy.gpx import TimeBounds
import datetime

class GPXRecorder:
      def __init__(self, url, storage ):
          self.url = url
          self.mqttc = mqtt.Client()
          if url.username!=None:
              self.mqttc.username_pw_set( url.username, url.password )

          self.mqttc.on_connect = self.on_mqtt_connect
          self.mqttc.on_message = self.on_mqtt_message
          self.storage = storage
          self.counters = {}
          self.load_counters()

      def start(self):
          self.mqttc.connect( self.url.hostname, self.url.port if self.url.port!=None else 1883, 60 )
          # mqtt broker
          logging.info("Trying connect to MQTT broker at %s:%d" % (self.url.hostname, self.url.port) )
          self.mqttc.loop_forever()
 

      def on_mqtt_connect(self, client, userdata, flags, rc):
          logging.info("MQTT broker connection result: %s", mqtt.connack_string(rc) )
          if rc==0:
             client.subscribe("owntracks/#", 0)
          pass

      def on_mqtt_message(self, client, userdata, message):
          logging.debug("Got mqtt message: %s %s", message.topic, message.payload )
          d = message.topic.split("/")
          device, tracker = (d[1],d[2])

          try:
             data = {}
             try:
                data = json.loads(message.payload)
             except:
                try:
                   s = zlib.decompress(message.payload, 16+zlib.MAX_WBITS) #gzip.decompress(message.payload).decode("utf-8")
                   # logging.info("Decompressed data: %s", s)
                   data = json.loads(s)
                except:
                   pass

             if "track" in data:
                gpx = self.track2gpx( data["track"] )

                start_time = self.get_time_bounds( gpx ).start_time or datetime.datetime.now()

                filename = "%s-%s.gpx" % (device, start_time.strftime("%Y_%m_%d-%H_%M") )
                logging.info("Storing track to %s", filename)

                f = open( os.path.join(self.storage, filename), "wb" )
                f.write( gpx.to_xml() )
                f.close()

                self.publish_stat(client, device, tracker, gpx )
          except:
             logging.exception("Error while process data from MQTT")
          pass

      def get_time_bounds(self, gpx):
          start_time = None
          end_time = None
          for point in gpx.get_points_data():
              if point.point.time:
                 if start_time==None and point.distance_from_start>0:
                    start_time = point.point.time
                 end_time = point.point.time
          if start_time==None:
             start_time=end_time
          return TimeBounds(start_time,end_time)

      def load_counters(self):
          try:
             fp = open("trackrec.dat","rb")
             self.counters = json.load( fp )
             fp.close()
          except:
             pass
          pass

      def store_counters(self):
          try:
             fp = open("trackrec.dat","wt")
             json.dump(self.counters, fp )
             fp.close()
          except:
             pass
          pass

      def publish_stat(self, client, device, tracker, gpx):
          time_data = self.get_time_bounds( gpx )
          move_data = gpx.get_moving_data()

          move_time = (time_data.end_time - time_data.start_time).total_seconds()
          avg_speed = (move_data.moving_distance / move_time) if move_time!=0 else 0

          self.load_counters()

          if device not in self.counters:
             self.counters[device] = { 'odo': 0, 'engine_time': 0 }

          self.counters[device]['odo']         = self.counters[device]['odo'] + move_data.moving_distance/1000
          self.counters[device]['engine_time'] = self.counters[device]['engine_time'] + move_time/3600.0

          self.store_counters()

          stat = {
             '_type': 'stat',
             'move_time': move_time, 
             'avg_speed': avg_speed*3.6, 
             'max_speed': move_data.max_speed * 3.6, 
             'distance': move_data.moving_distance/1000
          }
          stat.update( self.counters[device] )
          logging.info( "Sendning stat for device:%s %s", device, json.dumps(stat) )
          client.publish( 'owntracks/%s/%s/stat' % (device,tracker),  json.dumps(stat), retain=True )
          pass

      def track2gpx(self, track):
          gpx = gpxpy.gpx.GPX()
          gpx_track = gpxpy.gpx.GPXTrack()
          gpx.tracks.append(gpx_track)
          gpx_segment = gpxpy.gpx.GPXTrackSegment()
          gpx_track.segments.append(gpx_segment)

          for idx, p in enumerate(track):
             point = gpxpy.gpx.GPXTrackPoint(
                  p["lat"], p["lon"], elevation= p['alt'] if 'alt' in p else None, time=datetime.datetime.utcfromtimestamp( p["tst"] ), speed=p["vel"] if 'vel' in p else None,
                  name = "Start" if idx==0 else ( "Finish" if idx==len(track)-1 else None )
             )
             gpx_segment.points.append( point )
          return gpx

if __name__ == "__main__":
   class LoadFromFile( argparse.Action ):
       def __call__ (self, parser, namespace, values, option_string = None):
          with values as f:
              parser.parse_args(f.read().split(), namespace)

   parser = argparse.ArgumentParser( fromfile_prefix_chars='@' )
   parser.add_argument( "--storage", default="/tmp/" )

   parser.add_argument( "-c", "--config", type=open, action=LoadFromFile, help="Load config from file" )
   parser.add_argument( "-u","--url", default="mqtt://localhost:1883", type=urlparse.urlparse )
   parser.add_argument( "-v", action="store_true", default=False, help="Verbose logging", dest="verbose" )
   parser.add_argument( "--logfile", help="Logging into file" )
   args = parser.parse_args()
   logging.basicConfig( format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",  level= logging.DEBUG if args.verbose else logging.INFO, filename=args.logfile )

   recorder = GPXRecorder( args.url, storage=args.storage )
   recorder.start()
