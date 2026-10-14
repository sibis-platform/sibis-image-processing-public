#!/bin/bash

FREESURFER_HOME=${1:-"/usr/local/tools/freesurfer"}

export FREESURFER_HOME
source ${FREESURFER_HOME}/SetUpFreeSurfer.sh
