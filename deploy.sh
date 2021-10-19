#!/usr/bin/env sh

set -x
git pull
docker pull tomasbedrich/xcontest-cashier:latest
mkdir -p data/
sudo chown -R ja:ja data/
docker-compose down
docker-compose up -d
