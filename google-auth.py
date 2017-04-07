import logging
import argparse
import httplib2
from apiclient import discovery
from apiclient.http import MediaIoBaseUpload
import oauth2client.client
import oauth2client.file
import sys


class LoadFromFile( argparse.Action ):
    def __call__ (self, parser, namespace, values, option_string = None):
       with values as f:
           parser.parse_args(f.read().split(), namespace)

parser = argparse.ArgumentParser( fromfile_prefix_chars='@' )
parser.add_argument( "--storage", default="googleapi.token" )
parser.add_argument( "--client_id", required=True )
parser.add_argument( "--secret", required=True )
parser.add_argument( "--scope", nargs="+" )

parser.add_argument( "--authcode", default=None )

parser.add_argument( "-c", "--config", type=open, action=LoadFromFile, help="Load config from file" )
parser.add_argument( "-v", action="store_true", default=False, help="Verbose logging", dest="verbose" )
parser.add_argument( "--logfile", help="Logging into file" )
args = parser.parse_args()
logging.basicConfig(format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",  level= logging.DEBUG if args.verbose else logging.INFO, filename=args.logfile )

storage = oauth2client.file.Storage( args.storage )

print args.scope
flow = oauth2client.client.OAuth2WebServerFlow( args.client_id, args.secret, args.scope, redirect_uri="http://localhost" )

if args.authcode==None:
   auth_url = flow.step1_get_authorize_url()
   logging.error("Open browser at %s and re-run with --authcode= argument", auth_url)
   sys.exit()

else:
   credentials = flow.step2_exchange( args.authcode )
   storage.put(credentials)
   logging.info("Google auth token stored in %s", args.storage )
