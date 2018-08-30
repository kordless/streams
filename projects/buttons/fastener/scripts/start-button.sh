#!/bin/bash
set -x
sudo su -

# ... Galvanize
#         (To arouse to awareness or action)

# hostname convention: button-<stream id>-<instance id>
SID=`hostname | cut -d '-' -f 2` # stream ID (aka app name)
IID=`hostname | cut -d '-' -f 3` # instance ID

echo "SID: $SID"
echo "IID: $IID"

# Look up details for stream $SID, say "lou"
# curl https://streams.lucidworks.com/api/stream/lou
# {'id': 'y4xt',
# 'fusion_version': '7.4',
# 'repo': 'https://github.com/lucidworks/streams/projects/sockitter/dev',
# etc....
# }

STREAM_JSON=`curl https://streams.lucidworks.com/api/stream/$SID`

# if [ "$SID" = "rules" ]; then
#   STREAM_JSON='{"sid": "rules", "fusion_version":"4.0.2", "distro": "rules-buttons.tgz", "admin_password": "password123"}'
# fi
#
# if [ "$SID" = "starter" ]; then
#   STREAM_JSON='{"sid": "starter", "fusion_version":"4.0.2", "distro": "starter-buttons.tgz", "admin_password": "password123"}'
# fi
#
# if [ "$SID" = "lou" ]; then
#   STREAM_JSON='{"sid": "lou", "fusion_version":"4.0.2", "distro": "lou-buttons.tgz", "admin_password": "password123"}'
# fi

if [ -z "$STREAM_JSON" ]; then
  echo "ERROR: No $SID stream metadata available"
  exit 42
fi

IP=$(wget -qO- http://ipecho.net/plain)

cd /; git clone https://github.com/lucidworks/streams

# First some Java...
add-apt-repository ppa:webupd8team/java -y
echo debconf shared/accepted-oracle-license-v1-1 select true | sudo debconf-set-selections
echo debconf shared/accepted-oracle-license-v1-1 seen true | sudo debconf-set-selections

apt-get update -y
apt-get install oracle-java8-installer -y
apt install oracle-java8-set-default -y
echo JAVA_HOME="/usr/lib/jvm/java-8-oracle" >> /etc/environment

# `jq` is in a different vivid universe
echo "deb http://us.archive.ubuntu.com/ubuntu vivid main universe" >> /etc/apt/sources.list
apt-get install jq -y
apt-get install unzip -y
apt-get install maven -y
apt-get install ant -y

DISTRO=`echo $STREAM_JSON | jq -r .distro`
FUSION_VERSION=`echo $STREAM_JSON | jq -r .fusion_version`
# ADMIN_PASSWORD=`echo $STREAM_JSON | jq -r .admin_password`
ADMIN_PASSWORD=`curl http://metadata.google.internal/computeMetadata/v1/instance/attributes/password -H "Metadata-Flavor: Google"`
FUSION_API_CREDENTIALS="admin:$ADMIN_PASSWORD"
FUSION_API_BASE=http://localhost:8764/api

echo "DISTRO: $DISTRO"

# only download and untar if we do not have a /fusion directory
if [ ! -d "/fusion" ]; then
# #############################
# # if fusion not installed
# #############################

gsutil cp gs://buttons-streams/fusion-${FUSION_VERSION}.tar.gz .

tar xfz fusion-${FUSION_VERSION}.tar.gz

# link up fusion
ln -s /fusion/ /root/fusion

# replace line in /fusion/conf/fusion.properties
sed -i "
s,solr.jvmOptions = -Xmx2g -Xss256k,solr.jvmOptions = -Xmx2g -Xss256k -Denable.runtime.lib=true,g;
" /fusion/${FUSION_VERSION}/conf/fusion.properties

# restart
/fusion/${FUSION_VERSION}/bin/fusion restart

# set the password
curl -X POST -H 'Content-type: application/json' -d "{\"password\":\"${ADMIN_PASSWORD}\"}" http://localhost:8764/api

# #############################
# # end if fusion not installed
# #############################
else
/fusion/bin/fusion restart

# stop, remove, restart webapps to get them working through 8764
# workaround for https://jira.lucidworks.com/browse/APOLLO-14303
/fusion/bin/webapps stop && rm /fusion/var/webapps/webapps/* && /fusion/bin/webapps start
fi

##
#    stream/app-specific handling
##


mkdir $SID
cd $SID

# TODO: conditional on DISTRO: fetch if specified, otherwise ignore
#   - if no DISTRO to fetch, then this becomes a simple Fusion out of the box, box

gsutil cp gs://buttons-streams/$DISTRO .
tar xfz $DISTRO

# check for existence (and executable-ness) of ./buttons-start.sh
export FUSION_API_BASE; export FUSION_API_CREDENTIALS; export ADMIN_USERNAME; export ADMIN_PASSWORD; export IP; ./buttons-start.sh

echo "$SID-$IID has been Galvanized"
