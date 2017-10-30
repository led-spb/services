#!/bin/sh

cd `dirname $0`

inotifywait -m -e create --format '%w%f' /home/pi/Downloads/Tracks/ 2>/dev/null | while read file ; do
    echo "New track recorded $file"
    image=${file%.*}.png
    python track2img.py --url @track2img.conf $file $image
    ln -s -f $image lasttrack.png
    python gdriveput.py --token gdrive.token $file /tracks/
done
