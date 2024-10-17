TRACK = 3
BUILD_DIRECTORY := ./build
FOLDER=./releases/$(TRACK)/kafka

clean:
	rm -rf $(BUILD_DIRECTORY)

lint:
	tox -e lint

build: clean lint
	mkdir -p $(BUILD_DIRECTORY)
	cp $(FOLDER)/bundle.yaml $(BUILD_DIRECTORY)/bundle.yaml
	cp $(FOLDER)/charmcraft.yaml $(BUILD_DIRECTORY)
	cp $(FOLDER)/metadata.yaml $(BUILD_DIRECTORY)
	cp $(FOLDER)/README.md $(BUILD_DIRECTORY)
	charmcraft pack --destructive-mode --project-dir $(BUILD_DIRECTORY) --output $(BUILD_DIRECTORY)

deploy: build
	juju deploy $(BUILD_DIRECTORY)/bundle.zip

release: build
	charmcraft upload $(BUILD_DIRECTORY)/*.zip --name kafka-bundle --release=$(TRACK)/edge
