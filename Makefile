prefix=$(CURDIR)/install
docker-build-opts =
ifdef docker-nocache
docker-build-opts += --no-cache
endif
SINGULARITY=apptainer
SINGULARITY_VERSION=$(shell $(SINGULARITY) --version | awk '{print $$3}')
IMG_NAME=sibis-image-processing
DOCKER_IMG=$(IMG_NAME):latest

# Accept only valid project names, default to sibis
VALID_PROJECTS := hivalc ncanda
raw_project := $(strip $(project))
ifeq ($(filter $(raw_project), $(VALID_PROJECTS)), )
override project := sibis
else
override project := $(raw_project)
endif

LINK_NAME=$(project)-image-processing
SINGULARITY_IMG=$(IMG_NAME)-latest
SINGULARITY_INSTALL=$(prefix)
IMG_DIR=images
SING_IMG=$(SINGULARITY_IMG)
BUILD_DIR=$(shell pwd)/build
APPTAINER_TMPDIR=/tmp/apptainer-tmp
APPTAINER_CACHEDIR=/tmp/apptainer-cache
DOCKER_BUILDKIT=1

# Patch builds (see PATCHES.md)
PATCH_TOOL=APPTAINER=$(SINGULARITY) APPTAINER_TMPDIR=$(APPTAINER_TMPDIR) APPTAINER_CACHEDIR=$(APPTAINER_CACHEDIR) python3 bin/patch-sif.py
patch-build-opts=--fakeroot

# install: an explicit sif=<path> wins; otherwise build/ must hold exactly one SIF
ifdef sif
INSTALL_SIF := $(sif)
else
INSTALL_SIF := $(filter-out %.FAILED.sif,$(wildcard $(BUILD_DIR)/*.sif))
endif
INSTALL_NAME = $(notdir $(INSTALL_SIF))
INSTALL_SIDECAR = $(INSTALL_SIF:.sif=.patches.json)

sif: SING_DATE_FULL := $$(docker inspect --format="{{.Created}}" $(DOCKER_IMG))
sif: SING_DATE := $$(docker inspect --format="{{.Created}}" $(DOCKER_IMG) | cut -c1-10)
sif: SING_ID := $$(docker inspect --format="{{.Id}}" $(DOCKER_IMG) | cut -c8-19 )
sif: SING_IMG := $(strip $(SINGULARITY_IMG)_$(SING_DATE)_$(SING_ID))
sif: SING_CONTAINER_IMG := $(SING_IMG).sif
sif: docker-image
	-mkdir -p $(BUILD_DIR)
	-mkdir -p $(APPTAINER_TMPDIR) $(APPTAINER_CACHEDIR)
	-rm -f $(BUILD_DIR)/$(SING_IMG).sif
	@echo "Creating singularity image: $(BUILD_DIR)/$(SING_IMG).sif"
	APPTAINER_TMPDIR=$(APPTAINER_TMPDIR) APPTAINER_CACHEDIR=$(APPTAINER_CACHEDIR) \
		$(SINGULARITY) build $(BUILD_DIR)/$(SING_IMG).sif docker-daemon://$(DOCKER_IMG)

docker-image:
	cd resources && DOCKER_BUILDKIT=1 docker build --progress=plain --tag $(DOCKER_IMG) --target runtime $(docker-build-opts) .

# Build a patched SIF on top of an existing base SIF:
#   make patch base=<path/to/base.sif> patches="atropos251 qatoolsfix"
patch:
	@test -n "$(base)" || { echo 'usage: make patch base=<base.sif> patches="name ..."' >&2; exit 2; }
	@test -n "$(patches)" || { echo 'usage: make patch base=<base.sif> patches="name ..."  (see: make patch-list base=...)' >&2; exit 2; }
	$(PATCH_TOOL) --base "$(base)" $(addprefix --patch ,$(patches)) --out-dir $(BUILD_DIR) --build-opts="$(patch-build-opts)"

# Show every patch and whether it applies to a base:  make patch-list base=<path/to/base.sif>
patch-list:
	@test -n "$(base)" || { echo 'usage: make patch-list base=<base.sif>' >&2; exit 2; }
	$(PATCH_TOOL) --base "$(base)" --list

# Pick an installed base and patches from prompts
patch-interactive:
	$(PATCH_TOOL) --interactive --images-dir $(SINGULARITY_INSTALL)/$(IMG_DIR) --out-dir $(BUILD_DIR) --build-opts="$(patch-build-opts)"

install:
	@if [ $(words $(INSTALL_SIF)) -ne 1 ]; then \
		echo "install: expected exactly one SIF, found $(words $(INSTALL_SIF)) in $(BUILD_DIR); pass sif=<path>" >&2; \
		exit 2; \
	fi
	@test -f "$(INSTALL_SIF)" || { echo "install: $(INSTALL_SIF) not found" >&2; exit 2; }
	-mkdir -p $(SINGULARITY_INSTALL)/$(IMG_DIR)
	cp -f $(INSTALL_SIF) $(SINGULARITY_INSTALL)/$(IMG_DIR)/
	-chown root:users $(SINGULARITY_INSTALL)/$(IMG_DIR)/$(INSTALL_NAME)
	@if [ -f "$(INSTALL_SIDECAR)" ]; then \
		cp -f "$(INSTALL_SIDECAR)" $(SINGULARITY_INSTALL)/$(IMG_DIR)/ && \
		echo "installed provenance $(notdir $(INSTALL_SIDECAR))"; \
	fi
ifdef link-latest
	rm -f $(SINGULARITY_INSTALL)/$(LINK_NAME)-latest.sif
	ln -s $(SINGULARITY_INSTALL)/$(IMG_DIR)/$(INSTALL_NAME) $(SINGULARITY_INSTALL)/$(LINK_NAME)-latest.sif
endif
ifdef link-stable
	rm -f $(SINGULARITY_INSTALL)/$(LINK_NAME)-stable.sif
	ln -s $(SINGULARITY_INSTALL)/$(IMG_DIR)/$(INSTALL_NAME) $(SINGULARITY_INSTALL)/$(LINK_NAME)-stable.sif
endif

clean-build:
	-rm -rf $(BUILD_DIR)/*

clean-work:
	-rm -rf $(BUILD_DIR)

clean-apptainer:
	-rm -rf $(APPTAINER_TMPDIR) $(APPTAINER_CACHEDIR)

.SUFFIXES:
.SUFFIXES: .sif .meta
.NOTPARALLEL:
.PHONY: sif docker-image patch patch-list patch-interactive install clean-build clean-work clean-apptainer
