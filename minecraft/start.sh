#!/bin/sh

while :
do
  docker-compose down # make sure we clean up our junk
  docker-compose run -p 25565:25565 minecraft
  echo "press CTRL-C to cancel restarting..."
  sleep 5
done
