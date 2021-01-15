#!/bin/sh

adduser -s /sbin/nologin -h /home/samba -H -D delta

smbd --foreground --log-stdout --no-process-group
