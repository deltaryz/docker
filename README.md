# Docker config files

All standard background services will be started by the `docker-compose.yml` file in the root directory by running `docker-compose up`. They will automatically be restarted if the application stops for any reason.

Non-24/7 services such as resource-intensive game servers will exist in their own folders with their own launch methods.
