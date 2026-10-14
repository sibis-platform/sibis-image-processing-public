ARG PREFIX=/usr/local/tools
ARG SRC_PREFIX=/usr/local/src
ARG BASE_IMAGE=ubuntu:24.04
ARG INIT_BIN=/ip_init/bin

### BASE #####

# syntax=docker/dockerfile:1.4
FROM ${BASE_IMAGE} AS base

ARG INIT_BIN
ARG SRC_PREFIX

ENV DEBIAN_FRONTEND="noninteractive"


# may need to move openjdk-8-jdk to base and delete jre
RUN apt-get -y update && \
    apt-get -y install \
        tzdata \
        locales \
        git-all \
        emacs \
        vim \
        subversion \
        unzip \
        zip \
        curl \
        tcsh \
        csh \ 
        cmake \
        rsync \
        strace \
        cmake-curses-gui \
        openjdk-8-jre \
        dc \
        bc \
        libfftw3-dev \
        libglu1-mesa-dev \
        libglw1-mesa-dev \
        libgsl-dev \
        build-essential \
	gawk \
        && rm -rf /var/lib/apt/lists/*

ARG SRC_PREFIX=/usr/local/src
RUN mkdir -p ${SRC_PREFIX}
RUN mkdir -p ${INIT_BIN}

RUN ln -fs /usr/share/zoneinfo/America/Los_Angeles /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata

RUN  locale-gen en_US en_US.UTF-8 && dpkg-reconfigure locales

### BUILDER #####

# syntax=docker/dockerfile:1.4
FROM base AS builder

RUN apt-get -y update && \
    apt-get -y install \
        manpages-dev \
        software-properties-common \
        gdb \
        valgrind \
        openjdk-8-jdk \
        && rm -rf /var/lib/apt/lists/*



### CMTK #####

# syntax=docker/dockerfile:1.4
FROM builder AS cmtk

ARG PREFIX
ARG CMTK_ARCHIVE=CMTK-3.4.0-Source.tar.gz
ARG CMTK_VERSION=cmtk-3.4.0

# May need to add dcmtk, qtbase5-dev, qt5-qmake
RUN apt-get -y update && \
    apt-get -y install \
        libfftw3-dev \
        zlib1g-dev \
        libsqlite3-dev \
        libc6-dev \
        gcc-10 \
        g++-10 \
        && rm -rf /var/lib/apt/lists/*

RUN add-apt-repository ppa:ubuntuhandbook1/ppa --yes

ARG CMTK_PATH=${PREFIX}/cmtk

ADD /cmtk/${CMTK_ARCHIVE} ${CMTK_PATH}

WORKDIR ${PREFIX}/cmtk
RUN mkdir ./build

WORKDIR ${PREFIX}/cmtk/build

# Set compiler version to gcc/g++ 10
RUN update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-10 10
RUN update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-10 10

RUN cmake ${CMTK_PATH}/${CMTK_VERSION} -DCMAKE_INSTALL_PREFIX=${CMTK_PATH}
RUN cmake --build . --config Release --target install


### FSL #####

# syntax=docker/dockerfile:1.4
FROM builder AS fsl

ARG PREFIX

ADD /fsl/fslinstaller.py ${PREFIX}/fslinstaller.py
#ADD /fsl/fslinstaller_old.py ${PREFIX}/fslinstaller_old.py

WORKDIR ${PREFIX}

ENV FSL_INSTALL_LOG ${PREFIX}/fsl_installler.log

#RUN python3 fslinstaller.py -d ${PREFIX}/fsl -q -B 6.0.5.2 2>&1 | tee ${FSL_INSTALL_LOG}
RUN mkdir -p ${PREFIX}/fsl 
#RUN python3 fslinstaller.py -V 6.0.7.4 -d ${PREFIX}/fsl --no_shell 2>$1 | tee ${FSL_INSTALL_LOG}
RUN python3 fslinstaller.py --fslversion 6.0.7.4 --dest ${PREFIX}/fsl --no_env --overwrite


#RUN error_file=$(grep "fslpython_miniconda_installer.log" "${FSL_INSTALL_LOG}" | sed 's!^[^/]*!!' | cut -d ' ' -f 1 ) && \
#   if [ -e "$error_file" ]; then \
#     cat "$error_file"; \
#     cp "$error_file" ${PREFIX}/; \
#     exit 1; \
#   else \
#     echo "No FSL Install Errors"; \
#   fi

ENV FSLDIR=${PREFIX}/fsl 
ENV FSLPATH=${PREFIX}/fsl/bin
ENV PATH=${FSLPATH}:$PATH

RUN mv fslinstaller.py ${FSLDIR}

FROM fsl as fsl_done
### Freesurfer #####

# syntax=docker/dockerfile:1.4
FROM builder AS freesurfer

ARG PREFIX
ARG FREESURFER_ARCHIVE=freesurfer-linux-ubuntu22_amd64-7.3.2.tar.gz
LABEL FREESURFER_VERSION=7.3.2

ADD /freesurfer/${FREESURFER_ARCHIVE} ${PREFIX}
ADD /freesurfer/license.txt ${PREFIX}/freesurfer/

ENV FREESURFER_HOME=${PREFIX}/freesurfer
ADD /freesurfer/setup.sh /tmp
RUN /tmp/setup.sh ${PREFIX}/freesurfer

WORKDIR ${FREESURFER_HOME}

RUN ./bin/fs_install_mcr R2019b


### CONNECTOME #####

# syntax=docker/dockerfile:1.4
FROM builder as connectome

ARG INIT_BIN
ARG PREFIX
ARG CONNECTOME_VERSION=1.5.0
ARG CONNECTOME_ARCHIVE=workbench-linux64-v${CONNECTOME_VERSION}.zip
LABEL CONNECTOME_VERSION=${CONNECTOME_VERSION}

ADD /connectome/${CONNECTOME_ARCHIVE} ${PREFIX}/connectome/

WORKDIR ${PREFIX}/connectome

RUN unzip ${CONNECTOME_ARCHIVE} && \
    rm ${CONNECTOME_ARCHIVE}

ENV CONNECTOME_HOME=${PREFIX}/connectome/workbench/bin_linux64
ENV PATH=${PATH}:${CONNECTOME_HOME}

RUN echo "PATH=\$PATH:${CONNECTOME_HOME}" >> ${INIT_BIN}/init_bashrc

### LWDP #####

# syntax=docker/dockerfile:1.4
FROM builder AS lwdp

ARG PREFIX
ARG LWDP_SRC=r23
LABEL LWDP_VERSION=23

ADD /lwdp/${LWDP_SRC} ${PREFIX}/lwdp/${LWDP_SRC}


### ROBEX #####

# syntax=docker/dockerfile:1.4
FROM builder as robex

ARG PREFIX
ARG ROBEX_ARCHIVE=ROBEXv12.linux64.tar.gz
ARG ROBEX_VERSION=1.2

LABEL ROBEX_VERSION=${ROBEX_VERSION}

ADD /robex/${ROBEX_ARCHIVE} ${PREFIX}/robex/v${ROBEX_VERSION}


### NAONLM3D #####

# syntax=docker/dockerfile:1.4
FROM builder as naonlm3d

ARG PREFIX
ARG NAONLM3D_SHA=cf4d499f52c517101b9a6b97bbbb8b4b3e0f250d
LABEL NAONLM3D_SHA=${NAONLM3D_SHA}

ADD /naonlm3d/naonlm3d-src ${PREFIX}/naonlm3d
RUN mkdir ${PREFIX}/naonlm3d/build
WORKDIR ${PREFIX}/naonlm3d/build

RUN cmake ../ && \
    cmake --build . --config Release && \
    cmake --install . --prefix ${PREFIX}/naonlm3d


### CAMINO #####

# syntax=docker/dockerfile:1.4
from builder as camino

ARG PREFIX
ARG CAMINO_HASH=1c4ef77615d103d43adcff6c79b72d0bbdac0897
ARG CAMINO_ARCHIVE=camino-code-${CAMINO_HASH}.zip

ADD /camino/${CAMINO_ARCHIVE} ${PREFIX}/camino.zip
WORKDIR ${PREFIX}

RUN unzip camino.zip && \
    mv camino-code-${CAMINO_HASH} camino && \
    rm camino.zip

WORKDIR ${PREFIX}/camino

RUN make


### MINICONDA #####
# syntax=docker/dockerfile:1.4
from builder as miniconda

ARG PREFIX
ARG MINICONDA_ARCHIVE=Miniconda3-py39_4.12.0-Linux-x86_64.sh
ARG MINCONDA_ENV=ncanda-3.0.0-environment.yml

ADD /miniconda/${MINICONDA_ARCHIVE} ${PREFIX}/miniconda/miniconda.sh 

RUN chmod +x ${PREFIX}/miniconda/miniconda.sh

WORKDIR ${PREFIX}/miniconda

RUN bash miniconda.sh -b -f -p ${PREFIX}/miniconda

ADD /miniconda/${MINCONDA_ENV} ${PREFIX}/miniconda/environment.yml

ENV PATH="${PREFIX}/miniconda/bin:${PATH}"
#RUN conda update -y conda
RUN conda update -y -n base -c defaults conda
RUN conda update -y -n base -c defaults pip
RUN conda env create -f ${PREFIX}/miniconda/environment.yml 

### AFNI #####
from builder as afni 

ARG PREFIX
# ARG AFNI_ARCHIVE=linux_ubuntu_16_64.tgz
# ARG AFNI_ARCHIVE_VERSION=linux_ubuntu_16_64
# ARG COMMAND_DIR=command_scripts

# ARG COMMAND_2=step_2_afnibin_offline.tcsh
# ARG COMMAND_3=step_3_rinstall.tcsh
# ARG COMMAND_4=step_4_cleanup.tcsh

RUN add-apt-repository universe

RUN apt-get -y update && \
    apt-get install -y tcsh xfonts-base libssl-dev       \
                        python-is-python3                 \
                        python3-matplotlib python3-numpy  \
                        python3-flask python3-flask-cors  \
                        python3-pil                       \
                        gsl-bin netpbm gnome-tweaks       \
                        libjpeg62 xvfb xterm vim curl     \
                        gedit evince eog                  \
                        libglu1-mesa-dev libglw1-mesa-dev \
                        libxm4 build-essential            \
                        libcurl4-openssl-dev libxml2-dev  \
                        libgfortran-14-dev libgomp1       \
                        gnome-terminal nautilus           \
                        firefox xfonts-100dpi             \
                        r-base-dev cmake bc git           \
                        libgdal-dev libopenblas-dev       \
                        libnode-dev libudunits2-dev

# RUN apt-get -y update && \
#     apt-get -y install \
#         xfonts-base \
#         libssl-dev \
#         python-is-python3 \
#         python3-matplotlib \
#         python3-numpy \
#         gsl-bin \
#         netpbm \
#         gnome-tweaks \
#         libjpeg62 \
#         xvfb \
#         xterm \
#         gedit \
#         evince \
#         eog \
#         libglu1-mesa-dev \
#         libglw1-mesa \
#         libxm4 \
#         libcurl4-openssl-dev \
#         libxml2-dev \
#         libgfortran-11-dev \
#         libgomp1 \
#         gnome-terminal \
#         nautilus \
#         firefox \
#         xfonts-100dpi \
#         r-base-dev \
#         libgdal-dev \
#         libopenblas-dev \
#         libnode-dev \
#         libudunits2-dev \
#         && rm -rf /var/lib/apt/lists/* 

# COPY /afni/@update.afni.binaries ${PREFIX}/afni/
# COPY /afni/CD.tgz ${PREFIX}/afni/

# COPY /afni/${AFNI_ARCHIVE} ${PREFIX}/afni/${AFNI_ARCHIVE}
# ADD /afni/${COMMAND_DIR} ${PREFIX}/afni/install_commands

# RUN chmod -R +x ${PREFIX}/afni/install_commands

WORKDIR ${PREFIX}/afni

RUN curl -O https://raw.githubusercontent.com/afni/afni/master/src/other_builds/OS_notes.linux_ubuntu_24_64_a_admin.txt
RUN curl -O https://raw.githubusercontent.com/afni/afni/master/src/other_builds/OS_notes.linux_ubuntu_24_64_b_user.tcsh
RUN curl -O https://raw.githubusercontent.com/afni/afni/master/src/other_builds/OS_notes.linux_ubuntu_24_64_c_nice.tcsh
RUN bash OS_notes.linux_ubuntu_24_64_a_admin.txt 
RUN touch ~/.cshrc && tcsh OS_notes.linux_ubuntu_24_64_b_user.tcsh 
RUN tcsh OS_notes.linux_ubuntu_24_64_c_nice.tcsh

RUN echo "${PREFIX}/afni/abin"
RUN mv /root/abin ${PREFIX}/afni/
RUN ls -l ${PREFIX}/afni/abin

ENV HOME=${PREFIX}/afni
ENV AFNI_HOME=${PREFIX}/afni/abin
ENV PATH=${AFNI_HOME}:${PATH}

# RUN ln -s /usr/lib/x86_64-linux-gnu/libgsl.so.27 /usr/lib/x86_64-linux-gnu/libgsl.so.19

# RUN touch ~/.cshrc

# RUN [ "/bin/tcsh", "-c", "${PREFIX}/afni/install_commands/${COMMAND_2}"]
# RUN [ "/bin/tcsh", "-c", "${PREFIX}/afni/install_commands/${COMMAND_3}"]
# RUN [ "/bin/tcsh", "-c", "${PREFIX}/afni/install_commands/${COMMAND_4}"]


#ENV PATH=/root/abin/:${PATH}


# RUN /root/abin/afni_system_check.py -check_all
#RUN R --version
RUN afni_system_check.py -check_all

### ANTS #####
from builder as ants 

ARG PREFIX
ARG ANTS_PATH=/usr/local/tools/ants/install/bin
ARG SETUP_FILE=setup.sh

RUN apt-get -y update && \
    apt-get -y install \
        zlib1g-dev \
        && rm -rf /var/lib/apt/lists/*

ADD /ants/${SETUP_FILE} ${PREFIX}/ants/${SETUP_FILE}

WORKDIR ${PREFIX}/ants

RUN chmod +x ${SETUP_FILE}

RUN bash ${SETUP_FILE}

ENV ANTSPATH=${ANTS_PATH}
ENV PATH=${ANTSPATH}:$PATH


### C3D #####
from builder as c3d

ARG PREFIX
ARG C3D_Archive=/c3d-1.3.0-Linux-gcc64.tar.gz
ARG C3D_VERSION=c3d-1.3.0-Linux-gcc64
ARG C3D_PATH=${PREFIX}/c3d/${C3D_VERSION}

ADD /c3d/${C3D_Archive} ${PREFIX}/c3d

WORKDIR ${PREFIX}/c3d

ENV C3DPATH=${C3D_PATH}/bin
ENV PATH=${C3DPATH}:$PATH

### RESOURCES

# syntax=docker/dockerfile:1.4
FROM base AS resources

ARG PREFIX

COPY --link --from=afni     ${PREFIX} ${PREFIX} 
COPY --link --from=ants  ${PREFIX} ${PREFIX}
COPY --link --from=c3d  ${PREFIX} ${PREFIX}
COPY --link --from=camino  ${PREFIX} ${PREFIX}
COPY --link --from=cmtk  ${PREFIX} ${PREFIX}
COPY --link --from=connectome  ${PREFIX} ${PREFIX}
COPY --link --from=freesurfer ${PREFIX} ${PREFIX}
COPY --link --from=lwdp ${PREFIX} ${PREFIX}
COPY --link --from=miniconda ${PREFIX} ${PREFIX}
COPY --link --from=naonlm3d  ${PREFIX} ${PREFIX}
COPY --link --from=robex ${PREFIX} ${PREFIX}
COPY --link --from=fsl ${PREFIX} ${PREFIX}

ADD /slicer/slicer.tar.gz ${PREFIX}/slicer

RUN ln -s /usr/lib/x86_64-linux-gnu/libgsl.so.27 /usr/lib/x86_64-linux-gnu/libgsl.so.19
RUN rm -rf ${PREFIX}/__MACOSX


### RUNTIME #####
FROM resources AS runtime

# Add apps that are only used for runtime, not needed for building other layers.
RUN apt-get -y update && \
    apt-get -y install \
        imagemagick \
        && rm -rf /var/lib/apt/lists/*

# Add NCANDA user for data and running scripts
RUN groupadd ncanda -g 1023 && \
    useradd -ms /bin/bash ncanda -u 1023 -g 1023 -d /home/ncanda

# Add Sibis user for image processing ownership
RUN groupadd sibis -g 1001 && \
    useradd -ms /bin/bash sibis -u 1001 -g 1001 -d /home/sibis

ENV PATH=/usr/local/tools/image_processing/bin:/usr/local/tools/bin:${PATH}
RUN mkdir -p /usr/local/tools/bin && \
    ln -s /usr/local/tools/fsl/fslpython/bin/python /usr/local/tools/bin/fslpython

WORKDIR ${PREFIX}

RUN chown -R sibis:ncanda .

