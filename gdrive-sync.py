import argparse
import logging
import httplib2
from io import BytesIO
import time
from apiclient import discovery
from apiclient.http import MediaFileUpload
import datetime
import mimetypes
import oauth2client.client
from oauth2client.file import Storage
import os.path
import sys
from watchdog.observers import Observer
import  watchdog.events


class GDriveSync(watchdog.events.FileSystemEventHandler):

    def __init__(self, storage, path, target ):
        mimetypes.init()
        self.observer = Observer()
        self.path = path

        self.storage = Storage( storage )
        self.credentials  = self.storage.get()
        if not self.credentials or self.credentials.invalid:
           logging.error("Need actually google credentionals. Use google-auth.py")
           sys.exit()

        http = self.credentials.authorize(httplib2.Http())
        self.gdrive = discovery.build('drive', 'v3', http=http )

        self.folder = None
        if target!=None:
           folders = self.gdrive.files().list( q = "name = '%s' and mimeType = 'application/vnd.google-apps.folder'" % target ).execute().get('files',[])
           if len(folders)==0:
              self.folder = self.gdrive.files().create( body={ 'name': '%s', 'mimeType': 'application/vnd.google-apps.folder' % target } ).execute()
           else:
              self.folder = folders[0]
           logging.info( "Use folder %s id=%s", self.folder['name'], self.folder['id'] )
        pass

    def on_created(self, event):
        if isinstance(event, watchdog.events.FileCreatedEvent):
           filename = event.src_path
           logging.info("New file %s", filename )

           mimetype = mimetypes.guess_type(filename, False)
           mimetype = 'application/octet-stream' if mimetype==None else mimetype[0]

           media = MediaFileUpload( filename, chunksize=8*1024, mimetype= mimetype,resumable=True )
           body = { "name": os.path.basename(filename) }
           if self.folder!=None:
              body["parents"] = [ self.folder['id'] ]

           response = self.gdrive.files().create( body=body, media_body=media ).execute()
           logging.info("Stored id=%s", response['id'] )


    def start(self):
        self.observer.schedule( self, self.path )
        self.observer.start()
        try:
          while True:
             time.sleep(1)
        finally:
          self.observer.stop()
          self.observer.join()

if __name__ == "__main__":
   class LoadFromFile( argparse.Action ):
       def __call__ (self, parser, namespace, values, option_string = None):
          with values as f:
              parser.parse_args(f.read().split(), namespace)

   parser = argparse.ArgumentParser()
   parser.add_argument( "--storage", default="gdrive-sync.token" )

   parser.add_argument( "-c", "--config", type=open, action=LoadFromFile, help="Load config from file" )
   parser.add_argument( "-f", "--folder", default="." )
   parser.add_argument( "-t", "--target", default="sync" )
   parser.add_argument( "-v", action="store_true", default=False, help="Verbose logging", dest="verbose" )
   parser.add_argument( "--logfile", help="Logging into file" )
   args = parser.parse_args()
   logging.basicConfig(format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",  level= logging.DEBUG if args.verbose else logging.INFO, filename=args.logfile )

   sync = GDriveSync( args.storage, args.folder, args.target )
   sync.start()
