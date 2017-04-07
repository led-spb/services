#!/usr/bin/python 

import serial 
import time 
import struct 
import paho.mqtt.client as mqtt
import argparse, json
import logging
import urlparse

class BTPOWER:
   setAddrBytes      = [0xB4,0xC0,0xA8,0x01,0x01,0x00,0x1E]
   readVoltageBytes  = [0xB0,0xC0,0xA8,0x01,0x01,0x00,0x1A]
   readCurrentBytes  = [0XB1,0xC0,0xA8,0x01,0x01,0x00,0x1B]
   readPowerBytes    = [0XB2,0xC0,0xA8,0x01,0x01,0x00,0x1C]
   readRegPowerBytes = [0XB3,0xC0,0xA8,0x01,0x01,0x00,0x1D]

   def __init__(self, com, timeout=10.0):
      self.ser = serial.Serial(
         port=com,
         baudrate=9600,
         parity=serial.PARITY_NONE,
         stopbits=serial.STOPBITS_ONE,
         bytesize=serial.EIGHTBITS,
         timeout = timeout
      )
      if self.ser.isOpen():
         self.ser.close()
      self.ser.open()

   def checkChecksum(self, _tuple):
      _list = list(_tuple)
      _checksum = _list[-1]
      _list.pop()
      _sum = sum(_list)
      if _checksum == _sum%256:
         return True
      else:
         raise Exception("Wrong checksum")
         
   def isReady(self):
      self.ser.write(serial.to_bytes(self.setAddrBytes))
      rcv = self.ser.read(7)
      if len(rcv) == 7:
         unpacked = struct.unpack("!7B", rcv)
         if(self.checkChecksum(unpacked)):
            return True
      else:
         raise serial.SerialTimeoutException("Timeout setting address")

   def readVoltage(self):
      self.ser.write(serial.to_bytes(self.readVoltageBytes))
      rcv = self.ser.read(7)
      if len(rcv) == 7:
         unpacked = struct.unpack("!7B", rcv)
         if(self.checkChecksum(unpacked)):
            tension = unpacked[2]+unpacked[3]/10.0
            return tension
      else:
         raise serial.SerialTimeoutException("Timeout reading tension")

   def readCurrent(self):
      self.ser.write(serial.to_bytes(self.readCurrentBytes))
      rcv = self.ser.read(7)
      if len(rcv) == 7:
         unpacked = struct.unpack("!7B", rcv)
         if(self.checkChecksum(unpacked)):
            current = unpacked[2]+unpacked[3]/100.0
            return current
      else:
         raise serial.SerialTimeoutException("Timeout reading current")

   def readPower(self):
      self.ser.write(serial.to_bytes(self.readPowerBytes))
      rcv = self.ser.read(7)
      if len(rcv) == 7:
         unpacked = struct.unpack("!7B", rcv)
         if(self.checkChecksum(unpacked)):
            power = unpacked[1]*256+unpacked[2]
            return power
      else:
         raise serial.SerialTimeoutException("Timeout reading power")

   def readRegPower(self):
      self.ser.write(serial.to_bytes(self.readRegPowerBytes))
      rcv = self.ser.read(7)
      if len(rcv) == 7:
         unpacked = struct.unpack("!7B", rcv)
         if(self.checkChecksum(unpacked)):
            regPower = unpacked[1]*256*256+unpacked[2]*256+unpacked[3]
            return regPower
      else:
         raise serial.SerialTimeoutException("Timeout reading registered power")

   def readAll(self):
      if(self.isReady()):
         return(self.readVoltage(),self.readCurrent(),self.readPower(),self.readRegPower())
   def close(self):
      self.ser.close()




class EnergyMeter:
   def __init__( self, mqtt_url, com, store ):
       self.mqtt_url = mqtt_url
       self.com = com
       self.store = store
       self.sensor = None
       self.old_counter = 0

       self._mqtt_init( self.mqtt_url )
       self.counters = { "tariff1": 0, "tariff2": 0, "day": 0, "week": 0, "month": 0 }
       self.measure = {}
       try:
         self.counters.update( json.load( self.store ) )
       except:
         pass
       logging.info( "Current counters: %s" % json.dumps(self.counters, indent=4) )
       pass

   def _mqtt_init(self, url):
       self.mqttc = mqtt.Client()
       if url.username!=None:
          self.mqttc.username_pw_set( url.username, url.password )
       self.mqttc.on_connect = self.on_mqtt_connect
       self.mqttc.connect( url.hostname, url.port if url.port!=None else 1883, 60 )

       # mqtt broker
       logging.info("Trying connect to MQTT broker at %s:%d" % (url.hostname, url.port) )
       self.mqttc.loop_start()
       pass

   def on_mqtt_connect(self, client, userdata, flags, rc):
       logging.info("MQTT broker connection result: %s", mqtt.connack_string(rc) )
       pass

   def _store_counters(self):
       try:
         self.store.truncate(0)
         self.store.seek(0,0)
         json.dump( self.counters, self.store )
         args.store.flush()
       except:
         logging.exception('Error while store counters')

   def _inc_counters(self, delta):
       if delta<=0:
          return
       tm = time.localtime()

       if tm.tm_hour>=23 or tm.tm_hour<=6:
          self.counters["tariff2"] += delta
       else:
          self.counters["tariff1"] += delta

       # clear counters
       if tm.tm_hour==0 and tm.tm_min==0:
          self.counters["day"] = 0
          if tm.tm_wday==0:
             self.counters["week"] = 0
          if tm.tm_mday==1:
             self.counters["month"] = 0

       self.counters["day"]   += delta
       self.counters["week"]  += delta
       self.counters["month"] += delta
       pass


   def loop(self):
       if self.sensor == None:
          self.sensor = BTPOWER( self.com )

       try:
          # read power
          self.measure['regpower'] = self.sensor.readRegPower()
          self.measure['voltage']  = self.sensor.readVoltage()
          self.measure['current']  = self.sensor.readCurrent()
          self.measure['power']    = self.sensor.readPower()
       except:
          logging.exception('Error while read sensors')
          self.sensor.close()
          self.sensor = None
          return

       # calculate delta for counters
       if self.old_counter==0 or (self.measure["regpower"]-self.old_counter)<0:
          self.old_counter = self.measure["regpower"]
       delta = self.measure["regpower"]-self.old_counter
       self.old_counter = self.measure["regpower"]

       # append to counters
       self._inc_counters( delta )

       # append counters values
       self.measure.update( self.counters )

       # store accumulated energy counters
       self._store_counters()

       str_val = json.dumps(self.measure)

       logging.debug( str_val )
       self.mqttc.publish('/home/energy', str_val )
       


    
if __name__ == "__main__":
   class LoadFromFile( argparse.Action ):
       def __call__ (self, parser, namespace, values, option_string = None):
          with values as f:
              parser.parse_args(f.read().split(), namespace)

   parser = argparse.ArgumentParser( fromfile_prefix_chars='@' )
   parser.add_argument( "-c", "--config", type=open, action=LoadFromFile, help="Load config from file" )
   parser.add_argument( "-u","--url", default="localhost:1883", type=urlparse.urlparse )
   parser.add_argument( "--serial", default="/dev/ttyUSB0" )
   parser.add_argument( "--sleep", type=int, default=2 )

   parser.add_argument( "--store", type=argparse.FileType("r+"), default="energy.dat" )

   parser.add_argument( "-v", action="store_true", default=False, help="Verbose logging", dest="verbose" )
   parser.add_argument( "--logfile", help="Logging into file" )
   args = parser.parse_args()

   # configure logging
   logging.basicConfig(format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",  level= logging.DEBUG if args.verbose else logging.INFO, filename=args.logfile )

   meter = EnergyMeter( args.url, args.serial, args.store )
   while True:
      meter.loop()
      time.sleep( args.sleep )
