#!/usr/bin/python
import argparse
import logging
import httplib2
from apiclient import discovery
import apiclient.http
import mimetypes
import oauth2client.client
from oauth2client.file import Storage
import os.path
import sys
import json

if __name__ == "__main__":
   class LoadFromFile( argparse.Action ):
       def __call__ (self, parser, namespace, values, option_string = None):
          with values as f:
              parser.parse_args(f.read().split(), namespace)

   parser = argparse.ArgumentParser( fromfile_prefix_chars='@' )
   parser.add_argument( "-c", "--config", type=open, action=LoadFromFile, help="Load config from file" )

   parser.add_argument( "--token", default="gdrive.token" )
   parser.add_argument( "-v", action="store_true", default=False, help="Verbose logging", dest="verbose" )
   parser.add_argument( "--logfile", help="Logging into file" )

   parser.add_argument( "source" )
   parser.add_argument( "target" )

   args = parser.parse_args()

   logging.basicConfig(format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",  level= logging.DEBUG if args.verbose else logging.INFO, filename=args.logfile )

   mimetypes.init()

   target_dir, target_name = os.path.split( args.target.lstrip('/') )
   if target_name=='':
      target_name = os.path.basename(args.source)
   logging.info("storing %s to %s/%s" % (args.source, target_dir, target_name) )

   storage = Storage( args.token )
   credentials  = storage.get()
   if not credentials or credentials.invalid:
      logging.error("Need actually google credentionals. Use google-auth.py")
      sys.exit()

   http = credentials.authorize(httplib2.Http())
   gdrive = discovery.build('drive', 'v3', http=http )

   folder_id = gdrive.files().get( fileId='root', fields="id" ).execute().get('id', None)
   for folder_name in target_dir.split('/'):
       folders = gdrive.files().list( q="name = '%s' and mimeType = 'application/vnd.google-apps.folder' and '%s' in parents" % (folder_name, folder_id), fields="files(id,name)" ).execute().get('files',[])
       if len(folders)==0:
          logging.info("Creating folder: %s", folder_name )
          folder_id = gdrive.files().create( body={ 'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [folder_id] } ).execute().get('id', None)
       else:
          folder_id = folders[0]['id']
   logging.info("target folder id: %s", folder_id)

   mimetype = mimetypes.guess_type( args.source, False)
   mimetype = 'application/octet-stream' if mimetype==None or mimetype[0]==None else mimetype[0]

   media = apiclient.http.MediaIoBaseUpload( open(args.source,"rb"), chunksize=8*1024, mimetype=mimetype, resumable=True )
   response = gdrive.files().create( body={"name": target_name, "parents": [folder_id], 'mimeType': mimetype }, media_body=media ).execute()
   logging.info("Stored id=%s", response['id'] )
