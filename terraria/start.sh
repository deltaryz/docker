#!/bin/sh

while :
do
  docker-compose down # make sure we clean up our junk
  docker-compose run -p 7777:7777 terraria
  echo "press CTRL-C to cancel restarting..."
  sleep 5
done
