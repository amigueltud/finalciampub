#!/bin/bash

set -e -x
. build_helpers.inc.sh

trap "echo Unexpected error! See log above; exit 1" ERR

export BASE_IMAGE=$(get_value KEYCLOAK_IMAGE $f_BUILD)

export DOCKERFILE=$(get_value KEYCLOAK_DOCKERFILE $f_BUILD)
export IMAGE=$(get_value CIAM_KEYCLOAK_IMAGE $f_BUILD)

export MARIADB_CLIENT_KEYSTORE=$(get_value MARIADB_CLIENT_KEYSTORE $f_BUILD)

export KC_VERSION=$(get_value KEYCLOAK_VERSION $f_BUILD)

docker pull $BASE_IMAGE

mkdir -p keycloak || true

test ! -f keycloak/keycloak-$KC_VERSION.zip && (cd keycloak; wget https://github.com/keycloak/keycloak/releases/download/$KC_VERSION/keycloak-$KC_VERSION.zip; cd -)

test ! -f keycloak/$KC_VERSION.tar.gz && (cd keycloak; wget https://github.com/keycloak/keycloak/archive/refs/tags/$KC_VERSION.tar.gz; cd -)

mkdir ./keycloak/keycloak-${KC_VERSION}.kc_build || true
mkdir ./keycloak/keycloak-${KC_VERSION}.fspf_build || true

docker run --rm -it \
    --entrypoint bash \
    --env KC_VERSION=$KC_VERSION \
    --env JAVA_TOOL_OPTIONS="-Xmx2048m" \
    --env KEYCLOAK_HOME="/keycloak" \
    --env KEYCLOAK_ADMIN="configadmin" \
    --env KEYCLOAK_ADMIN_PASSWORD="0123456789" \
    --env KC_DB_SCHEMA=keycloak \
    --env KC_DB_URL='jdbc:mysql://mariadb/keycloak?user=ciam&password=0123456789&sslMode=trust&keyStore=/keycloak/mariadb.keystore&keyStorePassword=starterpasswd' \
    --env KC_DB=mariadb \
    --env KC_FEATURES=authorization,account2,account-api,docker,impersonation,upload-scripts,web-authn,client-policies,ciba,par,preview \
    --env KC_HTTPS_CERTIFICATE_FILE=/tls/keysrv.crt \
    --env KC_HTTPS_CERTIFICATE_KEY_FILE=/tls/keysrv-key.pem \
    --env KC_METRICS_ENABLED=true \
    -v $(pwd)/keycloak/keycloak-${KC_VERSION}.zip:/keycloak-${KC_VERSION}.zip \
    -v $(pwd)/keycloak/keycloak-${KC_VERSION}.kc_build:/keycloak \
    -v $(pwd)/credshandler/yield/mariadb.keystore:/mariadb.keystore.physical \
    openjdk:11 \
    -c '
    set -x;
    export PATH="$PATH:$KEYCLOAK_HOME/bin";
    rm -rf /keycloak/* || true;
    unzip -q /keycloak-${KC_VERSION}.zip;
    set +x;
    mv /keycloak-${KC_VERSION}/* /keycloak/;
    set -x;
    cd /keycloak;
    kc.sh build --db=$KC_DB;
    kc.sh show-config;
    '

####
# FSPF volume creation
#
if [[ ! -c "$DEVICE" ]] ; then
    export DEVICE_O="DEVICE"
    export DEVICE="/dev/isgx"
    if [[ ! -c "$DEVICE" ]] ; then
        echo "Neither $DEVICE_O nor $DEVICE exist"
        exit 1
    fi
fi

rm -rf ./keycloak/encrypted-files
rm -rf ./keycloak/native-files
rm -rf ./keycloak/fspf-file

mkdir ./keycloak/native-files
mkdir ./keycloak/encrypted-files
mkdir ./keycloak/fspf-file
cp ./keycloak/fspf.sh ./keycloak/fspf-file

docker run --rm --device=$DEVICE  -it \
    --env KC_VERSION=$KC_VERSION \
    -v $(pwd)/keycloak/keycloak-${KC_VERSION}.kc_build:/keycloak-${KC_VERSION}.kc_build \
    -v $(pwd)/keycloak/keycloak-${KC_VERSION}.fspf_build:/keycloak \
    -v $(pwd)/keycloak/fspf-file:/fspf/fspf-file \
    -v $(pwd)/keycloak/native-files:/fspf/native-files/ \
    -v $(pwd)/keycloak/encrypted-files:/fspf/encrypted-files \
    $BASE_IMAGE \
    /fspf/fspf-file/fspf.sh

docker build -f $DOCKERFILE --build-arg BASE_IMAGE=${BASE_IMAGE} --no-cache --build-arg KC_VERSION=$KC_VERSION -t $IMAGE --progress tty .

####
# CAS session creation
#
test ! -d keycloak/cas && mkdir keycloak/cas

export SCONE_FSPF_KEY=$(cat keycloak/native-files/keytag | awk '{print $11}')
export SCONE_FSPF_TAG=$(cat keycloak/native-files/keytag | awk '{print $9}')

export JAVA_MRENCLAVE="$(docker run --rm --device=$DEVICE -it $IMAGE bash -c "SCONE_HASH=1 SCONE_MODE=HW SCONE_HEAP=12G SCONE_FORK=1 java" |tr -d ' ' |tr -d '\n' |tr -d '\r')"

export MARIADB_KEYSTORE=`hexdump -ve '/1 "%02x"' $MARIADB_CLIENT_KEYSTORE`

KEYCLOAK_SESSION=$(get_value KEYCLOAK_SESSION $f_SESSIONS)
FLASK_SESSION=$(get_value FLASK_SESSION $f_SESSIONS)
MARIA_SESSION=$(get_value MARIA_SESSION $f_SESSIONS |cut -d ' ' -f 1)
CIAM_NAMESPACE=$(get_value CIAM_NAMESPACE $f_SESSIONS)

export KEYCLOAK_CLIENT_KEYSTORE=$(get_value KEYCLOAK_CLIENT_KEYSTORE $f_BUILD)
export KEYCLOAK_CLIENT_KEYSTORE_PASSWORD=-$(get_value KEYCLOAK_CLIENT_KEYSTORE_PASSWORD $f_BUILD)
export KEYCLOAK_KEYSTORE=deadbeef

export NAMESPACE_SESSION="$CIAM_NAMESPACE"
export TEMPLATE_FILE=keycloak-template_ciam.yml
export MRENCLAVE=$JAVA_MRENCLAVE
export SESSION_HASH=keycloak-session.hash
export APP_SESSION=$KEYCLOAK_SESSION
export PARTNER_SESSION="$FLASK_SESSION"
export SECOND_PARTNER_SESSION="$MARIA_SESSION"
export KEYCLOAK_PREDECESSOR=$(get_value KEYCLOAK_PREDECESSOR $f_BUILD)
export SAVE_CAS=1
(cd ./keycloak; ./session_upload.sh; cd -)

cat > ./keycloak/myenv << EOF
export KEYCLOAK_SESSION="$KEYCLOAK_SESSION"
export FLASK_SESSION="$FLASK_SESSION"
export SCONE_CAS_ADDR="$SCONE_CAS_ADDR"
export IMAGE="$IMAGE"
export DEVICE="$DEVICE"

EOF

echo "OK"
