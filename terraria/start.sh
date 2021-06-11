#!/bin/sh

while :
do
  docker-compose down # make sure we clean up our junk
  echo "press CTRL-C to cancel restarting..."
  sleep 5
  docker-compose run -p 7777:7777 terraria
done
