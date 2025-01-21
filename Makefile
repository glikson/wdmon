VERSION ?= latest
IMAGE_NAME = glikson/wdmon

.PHONY: build push all

all: build push

build:
	docker build -t $(IMAGE_NAME):$(VERSION) .

push:
	@if [ -z "$(DOCKER_PAT)" ]; then \
		echo "Error: DOCKER_PAT environment variable is not set"; \
		exit 1; \
	fi
	echo "$(DOCKER_PAT)" | docker login -u glikson --password-stdin
	docker push $(IMAGE_NAME):$(VERSION)
	docker logout
