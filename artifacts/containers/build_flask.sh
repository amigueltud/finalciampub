#!/bin/bash

set -e -x

. build_helpers.inc.sh

trap "echo Unexpected error! See log above; exit 1" ERR

export BASE_IMAGE=$(get_value FLASK_IMAGE $f_BUILD)

export DOCKERFILE=$(get_value FLASK_DOCKERFILE $f_BUILD)

export IMAGE=$(get_value CIAM_FLASK_IMAGE $f_BUILD)

export SCONE_CAS_ADDR="${SCONE_CAS_ADDR:-host.docker.internal}"
export CAS_MRENCLAVE="${CAS_MRENCLAVE:-edcba9876543210edcba9876543210edcba9876543210edcba9876543210edcb}"

export REDIS_IMAGE=$(get_value REDIS_IMAGE $f_BUILD)

export FLASK_SESSION=$(get_value FLASK_SESSION $f_SESSIONS)
export REDIS_SESSION=$(get_value REDIS_SESSION $f_SESSIONS)
export KEYCLOAK_SESSION=$(get_value KEYCLOAK_SESSION $f_SESSIONS)
export NAMESPACE_SESSION=$(get_value NAMESPACE_SESSION $f_SESSIONS)

# create directories for encrypted files and fspf
rm -rf encrypted-files
rm -rf native-files
rm -rf fspf-file

mkdir native-files/
mkdir encrypted-files/
mkdir fspf-file/
cp fspf.sh fspf-file
cp rest_api_ciam.py native-files/


# check if SGX device exists

if [[ ! -c "$DEVICE" ]] ; then
    export DEVICE_O="DEVICE"
    export DEVICE="/dev/isgx"
    if [[ ! -c "$DEVICE" ]] ; then
        echo "Neither $DEVICE_O nor $DEVICE exist"
        exit 1
    fi
fi

# create encrypted filesystem and fspf (file system protection file)
docker run --rm --device=$DEVICE  -it -v $(pwd)/fspf-file:/fspf/fspf-file -v $(pwd)/native-files:/fspf/native-files/ -v $(pwd)/encrypted-files:/fspf/encrypted-files $BASE_IMAGE /fspf/fspf-file/fspf.sh

# create a image with encrypted flask service
docker build -t $IMAGE --build-arg BASE_IMAGE=${BASE_IMAGE} .

# create session file

export SCONE_FSPF_KEY=$(cat native-files/keytag | awk '{print $11}')
export SCONE_FSPF_TAG=$(cat native-files/keytag | awk '{print $9}')

export FLASK_MRENCLAVE="$(docker run --rm --device=$DEVICE -it $IMAGE bash -c "SCONE_HASH=1 SCONE_FORK=1 python3" |tr -d ' ' |tr -d '\n' |tr -d '\r')"
export REDIS_MRENCLAVE="$(docker run --rm --device=$DEVICE -it --entrypoint sh $REDIS_IMAGE -c 'SCONE_HASH=1 SCONE_HEAP=1G redis-server' |tr -d ' ' |tr -d '\n' |tr -d '\r')"

export TEMPLATE_FILE=redis-template_ciam.yml
export MRENCLAVE=$REDIS_MRENCLAVE
export SESSION_HASH=redis-session.hash
export APP_SESSION=$REDIS_SESSION
export PARTNER_SESSION=$FLASK_SESSION
./session_upload.sh

export TEMPLATE_FILE=flask-template_ciam.yml
export MRENCLAVE=$PYTHON_MRENCLAVE
export SESSION_HASH=flask-session.hash
export APP_SESSION=$FLASK_SESSION
export PARTNER_SESSION=$REDIS_SESSION
export SECOND_PARTNER_SESSION=$KEYCLOAK_SESSION
./session_upload.sh

cat > myenv << EOF
export FLASK_SESSION="$FLASK_SESSION"
export REDIS_SESSION="$REDIS_SESSION"
export KEYCLOAK_SESSION="$KEYCLOAK_SESSION"
export SCONE_CAS_ADDR="$SCONE_CAS_ADDR"
export IMAGE="$IMAGE"
export DEVICE="$DEVICE"

EOF

echo "OK"
