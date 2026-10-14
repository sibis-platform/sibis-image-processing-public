#!/bin/bash


RELEASE="dev"
TARGET=
PURGE=1
RES_IMAGE_NAME="sibis-image-processing-resources"
POSITIONAL_ARGS=()

while [[ $# -gt 0 ]]; do

    case "$1" in

    -t|--target)
        TARGET="$2"
        shift
        shift
        ;;

    --release|--latest)
        RELEASE="latest"
        shift
        ;;

    --list)
        LIST=0
        shift
        ;;
    --purge)
        PURGE=0
        shift
        ;;

    *)
        POSITIONAL_ARGS="${POSITIONAL_ARGS} $1"
        shift
        ;;
    
    esac

done

eval set -- "${POSITIONAL_ARGS}"

DOCKER_BUILDKIT=1
export DOCKER_BUILDKIT

DOCKER_CONTEXT=$(dirname $0)

pushd ${DOCKER_CONTEXT}


if [[ ${LIST} ]]; then

    AVAIL_TARGETS=$(grep -ie "from .* as .*" Dockerfile | awk '{print $4}')
    echo ""
    echo "The available targets are:"
    for target in $AVAIL_TARGETS; do
        echo -e "\t$target"
    done
    exit 0
fi



if [[ ! -z "${TARGET}" ]]; then
    TAGNAME="${RES_IMAGE_NAME}:${TARGET}-${RELEASE}"
    TARGET="--target=${TARGET}"
else
    TAGNAME="${RES_IMAGE_NAME}:${RELEASE}"
fi

EXISTING_TAG=$(docker images -q ${TAGNAME})
if [[ ! -z "${EXISTING_TAG}" ]]; then
    TS=$(docker inspect --format "{{.Created}}" ${EXISTING_TAG})
    TS="${TS//[:-]/}"
    
    ARCHIVE_TAG="${TAGNAME}-${TS:0:15}"

    EXISTING_ARCHIVE=$(docker images -q ${ARCHIVE_TAG})
    if [[ -z "${EXISTING_ARCHIVE}" ]]; then 
        echo "Tagging exiting image with ${ARCHIVE_TAG}"
        docker tag ${EXISTING_TAG} ${ARCHIVE_TAG}
    else
        echo "Image exists with tag ${ARCHIVE_TAG}"
    fi
fi

docker build --progress=plain ${TARGET} --tag ${TAGNAME} . ${POSITIONAL_ARGS}
#docker buildx build --progress=plain ${TARGET} --tag ${TAGNAME} --builder "$(docker buildx create --driver-opt env.BUILDKIT_STEP_LOG_MAX_SIZE=10000000 --driver-opt env.BUILDKIT_STEP_LOG_MAX_SPEED=10000000)" . ${POSITIONAL_ARGS}


popd
