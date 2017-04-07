#!/usr/bin/python
# -*- coding: utf-8 -
import json
import paho.mqtt.client as mqtt
import tornado.websocket as websocket
import tornado.ioloop
import ssl
import time
import socket
import logging
import argparse
from urlparse import urlparse

class SSDPDiscovery():
   def __init__(self, ioloop=None):
       self.ioloop = ioloop if ioloop!=None else tornado.ioloop.IOLoop.current()

   def on_discovered(self, host, packet):
       if self._discovery_callback != None:
          self._discovery_callback( host, packet)
       pass

   def start(self, st, period=10000, callback = None):
       self.st = st
       self._discovery_callback = callback
       self._sock = socket.socket( socket.AF_INET, socket.SOCK_DGRAM )

       self._sock.setblocking( False )
       self._sock.setsockopt( socket.SOL_SOCKET, socket.SO_REUSEADDR, 1 )
       self._sock.setsockopt( socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2 )
       self.ioloop.add_handler( self._sock.fileno(), self._handle_events, tornado.ioloop.IOLoop.READ + tornado.ioloop.IOLoop.ERROR )

       self._discovery_loop()
       self._task = tornado.ioloop.PeriodicCallback( callback=self._discovery_loop, callback_time=period, io_loop=self.ioloop )
       self._task.start()
       pass

   def _discovery_loop(self):
       message = "\r\n".join([
              'M-SEARCH * HTTP/1.1',
              'HOST: 239.255.255.250:1900',
              'MAN: "ssdp:discover"',
              'MX: 3',
              'ST: {st}',
              '',''])
       self._sock.sendto( message.format( st=self.st ), ('239.255.255.250',1900) )
       pass

   def _handle_events(self, fd, event):
       if event==tornado.ioloop.IOLoop.READ:
          resp, address = self._sock.recvfrom(1024)
          self.on_discovered(address[0], resp)
       pass

   def stop(self):
       self._task.stop()
       pass



class MQTTClient(mqtt.Client):
      def __init__(self, ioloop=None ):
          mqtt.Client.__init__(self)
          self.ioloop = ioloop if ioloop!=None else tornado.ioloop.IOLoop.current()
          #self.on_log = self._log
          self.on_disconnect = self._disconnect
          self.fd = []

      def _log(self, client, userdata, level, buf):
          lvl = logging.INFO
          if level== mqtt.MQTT_LOG_WARNING:
             lvl = logging.WARNING
          if level== mqtt.MQTT_LOG_ERR:
             lvl = logging.ERROR
          if level== mqtt.MQTT_LOG_DEBUG:
             lvl = logging.DEBUG
          logging.log( lvl, buf )
          pass

      def _disconnect(self, client, userdata, rc ):
          for fd in self.fd:
             self.ioloop.remove_handler(fd)
          logging.info('Disconnected from MQTT broker (reason: %d)', rc)
          if rc!=0:
             self.try_reconnect()
          pass

      def try_reconnect(self):
          logging.debug('Connection attempt')
          try:
             self.reconnect()
          except socket.error:
             logging.debug('Connection failed, trying reconnect')
             self.ioloop.add_timeout( self.ioloop.time()+1, self.try_reconnect )

      def reconnect(self):
          mqtt.Client.reconnect(self)
          self.fd = [self._sockpairR.fileno(), self.socket().fileno()]
          for fd in self.fd:
             self.ioloop.add_handler( fd, self._mqtt_events, tornado.ioloop.IOLoop.READ+tornado.ioloop.IOLoop.ERROR )
          pass

      def connect(self, host, port):
          mqtt.Client.connect(self, host, port )

          self.schedule = tornado.ioloop.PeriodicCallback( callback=self.loop_misc, callback_time=10000, io_loop=self.ioloop )
          self.schedule.start()


      def _mqtt_events(self, fd, events):
          if self.socket()==None:
             return
          if True:# events & tornado.ioloop.IOLoop.READ:
             if fd==self.socket().fileno():
                self.loop_read()
             else:
                # signal for write
                self._sockpairR.recv(1)
                self.loop_write()
          pass



class LGRemote():
   def __init__(self, client_key=None, ioloop=None, on_register=None, on_close=None ):
       self.client_key = client_key
       self.ioloop = ioloop
       self.cmd_id = 0

       self.on_close = on_close
       self.on_register = on_register

   def connect(self, host, port=3000):
       self.cmd_id = 0
       self.requests = dict()
       websocket.websocket_connect( "ws://%s:%d" % (host,port), 
             io_loop  = self.ioloop,
             callback = self.on_open, 
             on_message_callback = self.on_message 
       )
       pass

   def on_error(self, exc):
       logging.error( "Error occured: %s", exc )

   def on_message(self, message):
       if message==None:
          if self.on_close!=None:
             self.on_close()
          return
       logging.debug(">>>%s", message )

       data = json.loads(message)
       request_id = data["id"]
       if request_id in self.requests.keys():
          callback = self.requests[request_id]
          callback( data )

   def on_open(self, future ):
       if future.exception()!=None:
          if self.on_close!=None:
             self.on_close()
          self.on_error( future.exception() )
          return

       self.socket = future.result()
       self.handshake(self.client_key, self.on_handshake )

   def on_handshake( self, data ):
       logging.debug('On registered')
       if data['type']=='registered':
          if self.on_register!=None:
             self.on_register( data )
       pass


   def command( self, msg_type, uri, payload, callback=None ):
       request_id = self.cmd_id
       self.cmd_id = self.cmd_id+1
       message = { "type": msg_type, "id": request_id }

       if uri!=None:
          message['uri'] = uri
       if payload!=None:
          message['payload'] = payload

       logging.debug("<<<%s", json.dumps(message) )
       if callback!=None:
          self.requests[ request_id ] = callback
          pass
       self.socket.write_message( json.dumps(message) )


   def handshake(self, client_key, callback):
       payload = {
          'forcePairing': False,
          'pairingType': 'PROMPT',
          'manifest': {
             'manifestVersion': 1,
             'appVersion': '1.1',
             'permissions': [
                  'LAUNCH',
                  'LAUNCH_WEBAPP',
                  'APP_TO_APP',
                  'CLOSE',
                  'TEST_OPEN',
                  'TEST_PROTECTED',
                  'CONTROL_AUDIO',
                  'CONTROL_DISPLAY',
                  'CONTROL_INPUT_JOYSTICK',
                  'CONTROL_INPUT_MEDIA_RECORDING',
                  'CONTROL_INPUT_MEDIA_PLAYBACK',
                  'CONTROL_INPUT_TV',
                  'CONTROL_POWER',
                  'READ_APP_STATUS',
                  'READ_CURRENT_CHANNEL',
                  'READ_INPUT_DEVICE_LIST',
                  'READ_NETWORK_STATE',
                  'READ_RUNNING_APPS',
                  'READ_TV_CHANNEL_LIST',
                  'WRITE_NOTIFICATION_TOAST',
                  'READ_POWER_STATE',
                  'READ_COUNTRY_INFO'      
               ]
          }
       }
       if client_key!=None:
          payload['client-key'] = client_key
       self.command( 'register', None, payload, callback=callback )
       pass


class MyLGRemote:

    def __init__(self, client_key=None, ioloop=None, mqtt_broker=('localhost',1883), auth=None):
        self.remote = LGRemote( client_key=client_key, ioloop=ioloop, on_close=self.on_close, on_register=self.on_register )

        self.info = { 'status': 0, 'channel': 'N/A', 'changed': int(time.time()), 'program': 'N/A', 'host': None }
        self.channels = []

        # start discovering via SSDP
        self._host = None
        self._discovery = SSDPDiscovery( ioloop )
        self._discovery.start( st='urn:lge-com:service:webos-second-screen:1', callback=self.on_discovered)

        # connect to MQTT server
        self._mqttc = MQTTClient( ioloop )
        self._mqttc.on_message = self.on_mqtt_message
        self._mqttc.on_connect = self.on_mqtt_connect
        if auth!=None:
           self._mqttc.username_pw_set( auth[0], auth[1] )
        self._mqttc.connect( mqtt_broker[0], mqtt_broker[1] )
        pass

    def parse_channel_name(self, name):
        parts = name.split(' ')
        if len(parts)>0 and parts[0].isdigit():
           parts = parts[1:]
        return ' '.join([x.capitalize() if len(x)>3 else x for x in parts ])

    def on_mqtt_connect(self, client, userdata, flags, rc):
        logging.info("MQTT connection: %s", mqtt.connack_string(rc) )
        if rc==0:
           self._mqttc.subscribe("/home/tv/control/#", 0)
           self.send_status()
        pass

    def on_mqtt_message(self, client, userdata, message):
        logging.debug("Got mqtt message: %s %s", message.topic, message.payload )
        command = "".join( message.topic.split('/home/tv/control/')[1:] )
        if hasattr(self, 'control_'+command ):
           func = getattr(self, 'control_'+command)
           func( message.payload )
        pass

    def on_discovered(self, host, packet ):
        if self.info['status']==0 and self._host==None:
           logging.info( "LGTV discovered: %s", host )
           self._host = host
           self.remote.connect( self._host )
        pass

    def send_status(self, changed=True):
        if changed:
           self.info['changed'] = int(time.time())
        logging.debug("Sending status: %s", json.dumps(self.info) )
        self._mqttc.publish( "/home/tv/detail", json.dumps(self.info), retain=True )

    def on_close(self):
        logging.info( "LGTV disconnected" )
        self._host = None
        self.info['host'] = None
        self.info['status'] = 0
        self.send_status()

    def on_register(self, data ):
        logging.info( "Connection established to %s", self._host )
        self.info['status'] = 1
        self.info['host'] = self._host

        self.remote.command('subscribe', 'ssap://tv/getCurrentChannel', None, self.on_channel_change)
        self.remote.command('request',   'ssap://tv/getChannelList', None, self.on_channel_list)
        #self.command('subscribe', 'ssap://audio/getStatus', None, self.on_audio_change)

    def on_channel_change(self, data):
        if 'payload' in data and 'channelName' in data['payload']:
           self.remote.command('request', 'ssap://tv/getChannelCurrentProgramInfo', None, self.on_program_info)
           self.info['channel'] = self.parse_channel_name( data['payload']['channelName'] )
           logging.info( "Channel changed to %s", self.info['channel']  )
           self.send_status()
        pass

    def on_program_info(self, data):
        if 'payload' in data and 'programName' in data['payload']:
           self.info['program'] = data['payload']['programName']
           self.send_status(False)
        pass

    def on_channel_list(self, data):
        if 'payload' in data and 'channelList' in data['payload']:
           self.channels = []
           logging.debug('Channels list')
           for ch in data['payload']['channelList']:
               id = ch['channelId']
               name = self.parse_channel_name( ch['channelName'] ).lower()
               self.channels.append( {'channelId':id, 'channelName': name} )
               logging.debug( "%s: %s", name, id )
        pass

    ##### control functions
    def control_power(self, status):
        if self.info['status'] == 0:
           self.send_status(False)
           return 
        self.remote.command('request', 'ssap://system/turnOff', None )
        pass

    def control_channel(self, channel):
        if self.info['status']==0:
           self.send_status(False)
           return 
        channelId = None
        channel = channel.lower()

        for ch in self.channels:
           if ch['channelName']==channel or ch['channelId']==channel:
              channelId = ch['channelId']
        if channelId!=None:
           self.remote.command('request', 'ssap://tv/openChannel', json.dumps({'channelId': channelId} ) )
        else:
           self.send_status(False)
        pass


if __name__ == '__main__':
    class LoadFromFile( argparse.Action ):
        def __call__ (self, parser, namespace, values, option_string = None):
           with values as f:
               parser.parse_args(f.read().split(), namespace)

    parser = argparse.ArgumentParser( fromfile_prefix_chars='@' )
    parser.add_argument( "-c", "--config", type=open, action=LoadFromFile, help="Load config from file" )
    parser.add_argument( "--url", default="mqtt://127.0.0.1:1883", type=urlparse )
    parser.add_argument( "--auth" )
    parser.add_argument( "-k", "--key" )
    parser.add_argument( "-v", action="store_true", default=False, help="Verbose logging", dest="verbose" )
    parser.add_argument( "--logfile", help="Logging into file" )
    args = parser.parse_args()

    # configure logging
    logging.basicConfig(format="[%(asctime)s] [%(levelname)-5s] %(message)s",  level=logging.DEBUG if args.verbose else logging.INFO, filename=args.logfile )

    ioloop = tornado.ioloop.IOLoop.instance()

    remote = MyLGRemote( 
               client_key=args.key, 
               ioloop=ioloop, 
               mqtt_broker=(args.url.hostname, args.url.port if args.url.port!=None else 1883), 
               auth=(args.url.username,args.url.password) if args.url.username!=None else None 
    )
    ioloop.start()


