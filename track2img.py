import logging
import gpxpy
import argparse
import urllib2

def encodeNumber(num):
    num = num << 1
    if num < 0:
      num = ~num
    encoded = ''
    while num >= 0x20:
       encoded = encoded + chr( (0x20 | (num & 0x1f)) + 63)
       num = num >> 5
    return encoded + chr(num + 63)

def display_gpx(gpx, namespace):
    namespace.lat_start = None
    namespace.lon_start = None

    namespace.lat_end = None
    namespace.lon_end = None

    namespace.lat_min = None
    namespace.lon_min = None

    namespace.lat_max = None
    namespace.lon_max = None

    encoded = ''
    oldLat = 0
    oldLon = 0

    for tr in gpx.tracks:
        for seg in tr.segments:
            for p in seg.points:
                if namespace.lat_min==None or namespace.lat_min>p.latitude: 
                   namespace.lat_min = p.latitude
                if namespace.lat_max==None or namespace.lat_max<p.latitude: 
                   namespace.lat_max = p.latitude
                if namespace.lon_min==None or namespace.lon_min>p.longitude: 
                   namespace.lon_min = p.longitude
                if namespace.lon_max==None or namespace.lon_max<p.longitude: 
                   namespace.lon_max = p.longitude

                if namespace.lat_start==None:
                   namespace.lat_start = p.latitude
                   namespace.lon_start = p.longitude

                namespace.lat_end = p.latitude
                namespace.lon_end = p.longitude

                ecenter='%f,%f' % (p.latitude, p.longitude )
                lat = int( p.latitude * 100000 )
                lon = int( p.longitude * 100000 )
                encoded = encoded + encodeNumber( lat - oldLat ) + encodeNumber(lon - oldLon)
                oldLat = lat
                oldLon = lon
                pass
    namespace.shape = encoded


if __name__ == "__main__":
   parser = argparse.ArgumentParser(fromfile_prefix_chars='@')
   parser.add_argument( "--url", required=True )
   parser.add_argument( "-v", action="store_true", default=False, help="Verbose logging", dest="verbose" )
   parser.add_argument( "--logfile", help="Logging into file" )
   parser.add_argument( "gpx_file" )
   parser.add_argument( "output", default="track.png" )
   args = parser.parse_args()

   logging.basicConfig( format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",  level= logging.DEBUG if args.verbose else logging.INFO, filename=args.logfile )

   gpx = gpxpy.parse( open(args.gpx_file,"r") )
   display_gpx(gpx, args)

   url = args.url.format( **{x[0]:x[1] for x in args._get_kwargs() } )
   logging.info( url )
   req = urllib2.urlopen( url )
   f = open(args.output,"wb")
   f.write( req.read() )
   f.close()
   logging.info("Track image saved to %s", args.output)
