import logging
import argparse
import urlparse
import paho.mqtt.client as mqtt
import json
import os.path
import gpxpy.gpx
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

      def start(self):
          self.mqttc.connect( self.url.hostname, self.url.port if self.url.port!=None else 1883, 60 )
          # mqtt broker
          logging.info("Trying connect to MQTT broker at %s:%d" % (self.url.hostname, self.url.port) )
          self.mqttc.loop_forever()
 

      def on_mqtt_connect(self, client, userdata, flags, rc):
          logging.info("MQTT broker connection result: %s", mqtt.connack_string(rc) )
          if rc==0:
             client.subscribe("owntracks/+/+/track", 0)
          pass

      def on_mqtt_message(self, client, userdata, message):
          logging.info("Got mqtt message: %s %s", message.topic, message.payload )
          d = message.topic.split("/")
          device, tracker = (d[1],d[2])

          data = json.loads(message.payload)
          if "track" in data:
             gpx = self.track2gpx( data["track"] )

             start_time = gpx.get_time_bounds().start_time
             filename = "%s-%s.gpx" % (device, start_time.strftime("%Y_%m_%d-%H_%M") )
             logging.info("Storing track to %s", filename)

             f = open( os.path.join(self.storage, filename), "wb" )
             f.write( gpx.to_xml() )
             f.close()
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
   parser.add_argument( "-u","--url", default="localhost:1883", type=urlparse.urlparse )
   parser.add_argument( "-v", action="store_true", default=False, help="Verbose logging", dest="verbose" )
   parser.add_argument( "--logfile", help="Logging into file" )
   args = parser.parse_args()
   logging.basicConfig( format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",  level= logging.DEBUG if args.verbose else logging.INFO, filename=args.logfile )

   recorder = GPXRecorder( args.url, storage=args.storage )
   recorder.start()
