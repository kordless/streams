#!/bin/bash

NEW_UUID=$(cat /dev/urandom | tr -dc 'a-z0-9' | fold -w 4 | head -n 1)
ZONE=us-west1-c
NAME=fastener-api

option=$1
PREEMPTIBLE="--preemptible"
IP="35.233.213.74" # dev IP

echo "This instance is preemtible, unless it's started with --prod";
case $option in
    -p|--prod|--production)
    unset PREEMPTIBLE
    IP="35.230.26.45" # production IP mapped to fastener.lucidworks.com
    echo "Production mode enabled..."
    echo;
esac

if [ -f secrets.sh ]; then
   source secrets.sh # truly, a travesty
   echo "Here's where I say, hold on a second while we fire things up."
   gcloud compute project-info add-metadata --metadata token=$TOKEN 
   echo;
else
   echo "Create 'secrets.sh', put a TOKEN=f00bar statement in it and then rerun this script."
   echo;
   exit;
fi

gcloud beta compute instances create $NAME-$NEW_UUID \
--machine-type "n1-standard-2" \
--image "ubuntu-1604-xenial-v20180627" \
--image-project "ubuntu-os-cloud" \
--boot-disk-size "50" \
--boot-disk-type "pd-ssd" \
--boot-disk-device-name "$NAME-disk-$NEW_UUID" \
--zone $ZONE \
--tags http-server,lucid,token-$TOKEN \
--scopes compute-rw \
--subnet=default --address=$IP --network-tier=PREMIUM \
--service-account labs-209320@appspot.gserviceaccount.com \
$PREEMPTIBLE \
--metadata startup-script='#! /bin/bash
sudo su -

apt-get update -y
apt-get install unzip -y
apt-get install build-essential -y
apt-get install python-dev -y
apt-get install python-setuptools -y
apt-get install python-paste -y
easy_install pip
pip install bottle
pip install google-cloud
pip install --upgrade google-api-python-client
pip install --upgrade pyasn1-modules
pip install google-auth-httplib2

#upgrade SSL
sudo mkdir /usr/local/share/ca-certificates/cacert.org
sudo wget -P /usr/local/share/ca-certificates/cacert.org http://www.cacert.org/certs/root.crt http://www.cacert.org/certs/class3.crt
sudo update-ca-certificates

cd /;
git clone https://github.com/lucidworks/streams
cd /streams/fastener/;
screen -dmS buttons bash -c "bash start-web.sh"
'

#gcloud compute instances attach-disk $NAME-$NEW_UUID --disk $NAME-data --zone $ZONE
gcloud compute firewall-rules create fastener-api --allow tcp:80

sleep 20
IP=$(gcloud compute instances describe $NAME-$NEW_UUID --zone $ZONE  | grep natIP | cut -d: -f2 | sed 's/^[ \t]*//;s/[ \t]*$//')

echo "Server started with $IP. Use the SSH button to login."
echo "Try http://$IP"
