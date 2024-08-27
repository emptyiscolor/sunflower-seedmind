all: prebuilt

prebuilt-docker:
	docker build -t prebuilt-docker .

prebuilt: prebuilt-docker
	docker run --rm -v $(CURDIR)/prebuilt:/app/prebuilt prebuilt-docker

clean:
	sudo rm -rf .tmp oss-fuzz/build

.PHONY: prebuilt-docker prebuilt all clean
