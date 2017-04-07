#!/bin/sh

cd `dirname $0`

inotifywait -m -e create --format '%w%f' /home/pi/Downloads/Tracks/ 2>/dev/null | while read file ; do
    echo "New track recorded $file"
    python track2img.py --url @track2img.conf $file track.png
    python gdriveput.py --token gdrive.token $file /tracks/
done