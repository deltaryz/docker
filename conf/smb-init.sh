#!/bin/sh

chown -R nobody.nobody /share
chmod -R 777 /share

smbd --foreground --log-stdout --no-process-group
