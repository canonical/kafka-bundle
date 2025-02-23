TRACK=3
TLS=true
COS_CONTROLLER=microk8s-localhost
COS_MODEL=cos
BUILD_DIRECTORY=./build
FOLDER=./releases/$(TRACK)/kafka

clean:
	rm -rf $(BUILD_DIRECTORY) parts prime stage

lint:
	tox -e lint

build: clean lint
	mkdir -p $(BUILD_DIRECTORY)

	TLS=$(TLS) BUILD_DIRECTORY=$(BUILD_DIRECTORY) FOLDER=$(FOLDER) COS_CONTROLLER=$(COS_CONTROLLER) COS_MODEL=$(COS_MODEL) tox -e render

	cd $(BUILD_DIRECTORY) && charmcraft pack --destructive-mode

deploy: build
	juju deploy $(BUILD_DIRECTORY)/bundle.zip

release: build
	charmcraft upload $(BUILD_DIRECTORY)/*.zip --name kafka-bundle --release=$(TRACK)/edge
