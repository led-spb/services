#!/usr/bin/python 
import serial 
import time, datetime
import struct 
import paho.mqtt.client as mqtt
import argparse, json
import logging
import urlparse, requests


class BTPOWER:
   setAddrBytes      = [0xB4,0xC0,0xA8,0x01,0x01,0x00,0x1E]
   readVoltageBytes  = [0xB0,0xC0,0xA8,0x01,0x01,0x00,0x1A]
   readCurrentBytes  = [0XB1,0xC0,0xA8,0x01,0x01,0x00,0x1B]
   readPowerBytes    = [0XB2,0xC0,0xA8,0x01,0x01,0x00,0x1C]
   readRegPowerBytes = [0XB3,0xC0,0xA8,0x01,0x01,0x00,0x1D]

   def __init__(self, com, baudrate=9600, timeout=10.0):
      self.ser = serial.Serial(
         port     = com,
         baudrate = baudrate,
         parity   = serial.PARITY_NONE,
         stopbits = serial.STOPBITS_ONE,
         bytesize = serial.EIGHTBITS,
         timeout  = timeout
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


class CounterStore:
   def __init__(self, format="json", interval="300"):
       self.format = Format.instances[format]
       self.interval = int(interval)
       self.data = {}
       pass

   def set_format(self, format):
       self.format = format

   def begin_store(self):
       self.data = {}
       pass

   def end_store(self):
       pass

   def get_data(self, name):
       return self.data[name]

   def set_data(self, name, data):
       self.data[name] = data
       pass


class FileStore(CounterStore):
   def __init__(self, format="json", interval="300", filename="energy.dat"):
       CounterStore.__init__(self,format)
       self.filename = filename
       self._read_data()

   def _read_data(self):
       self.data = {}
       try:
         f = open(self.filename, "rb")
         self.data = self.format.from_string( f.read() )
         f.close()
       except:
         pass

   def end_store(self):
       try:
         f = open(self.filename, "wb")
         f.write( self.format.to_string( self.data ) )
         f.close()
       except:
         pass

class TotalCounter:
   name = 'total'
   def __init__( self, store ):
       try:
         self.value, self.raw_value = store.get_data(self.name)
       except:
         self.value, self.raw_value = (0,0)
         pass


   def set_raw_value(self, tm, value ):
       delta = value - self.raw_value
       self.raw_value = value
       self.update( tm, delta )

   def update( self, tm, delta ):
       self.value = self.value + delta


class NightCounter(TotalCounter):
   name = 'night'
   def update( self, tm, delta ):
       if tm.hour >= 23 or tm.hour < 7:
          self.value = self.value + delta
       pass

class DayCounter(TotalCounter):
   name = 'day'
   def update( self, tm, delta ):
       if tm.hour >= 7 and tm.hour < 23:
          self.value = self.value + delta
       pass


class Format:
   instances = {}
   def __init__(self):
       Format.instances[ self.__class__.__name__.replace('Format','').lower() ] = self

   def to_string(self, data):
       return repr(data)

   def from_string(self, string):
       return eval(string)

class JSONFormat(Format):
   def to_string(self, data):
       return json.dumps(data)
   def from_string(self, string):
       return json.loads(string)

class EnergyMeter:
   def __init__( self, mqtt_url, com, counters, store ):
       self.mqtt_url = mqtt_url
       self.com = com
       self.store = store
       self.counters = counters

       self.sensor = None
       self._mqtt_init( self.mqtt_url )
       self.measure = {'regpower':0}

       logging.info( "Current counters")
       for c in self.counters:
           logging.info("%s: %d %d", c.name, c.value, c.raw_value)
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

   def loop(self):
       if self.sensor == None:
          self.sensor = BTPOWER( self.com )
       now = datetime.datetime.now()

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

       # update counters
       for counter in self.counters:
           counter.set_raw_value( now, self.measure['regpower'] )
           self.measure[ counter.name ] = counter.value

       str_val = json.dumps(self.measure)
       logging.debug( str_val )
       self.mqttc.publish('/home/sensor/energy', str_val )
      


    
if __name__ == "__main__":
   JSONFormat()
   counter_types = { x.replace('Counter','').lower(): globals()[x] for x in globals() if x.endswith('Counter') }
   store_types = { 'file': FileStore }

   class LoadFromFile( argparse.Action ):
       def __call__ (self, parser, namespace, values, option_string = None):
          with values as f:
              parser.parse_args(f.read().split(), namespace)

   parser = argparse.ArgumentParser( fromfile_prefix_chars='@' )
   parser.add_argument( "-c", "--config", type=open, action=LoadFromFile, help="Load config from file" )
   parser.add_argument( "-m","--mqtt", default="localhost:1883", type=urlparse.urlparse )
   parser.add_argument( "--counters", nargs="+", choices=counter_types.keys() )

   parser.add_argument( "--serial", default="/dev/ttyUSB0" )
   parser.add_argument( "--baudrate", type=int, default=9600 )
   parser.add_argument( "--update", type=int, default=2 )

   parser.add_argument( "--store", nargs="+", action="append" )

   parser.add_argument( "-v", action="store_true", default=False, help="Verbose logging", dest="verbose" )
   parser.add_argument( "--logfile", help="Logging into file" )
   args = parser.parse_args()


   storages = []
   for data in args.store:
       params = {} 
       storage_type = data[0]
       for d in data[1:]:
           w = d.split('=')
           params[w[0]]=w[1]
       storages.append( store_types[storage_type]( **params ) )

   # configure logging
   logging.basicConfig(format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",  level= logging.DEBUG if args.verbose else logging.INFO, filename=args.logfile )

   format = JSONFormat()
   store  = storages[0]
   counters = [ counter_types[x](store) for x in args.counters ]

   meter = EnergyMeter( args.mqtt, args.serial, counters, store )

   last_updated = 0
   while True:
      meter.loop()

      # store counters
      tm = int(time.time())/store.interval
      if last_updated - tm != 0:
         store.begin_store()
         try:
            for c in counters:
              store.set_data( c.name, (c.value,c.raw_value) )
         finally:
            store.end_store()
         last_updated = tm

      time.sleep( args.update )

