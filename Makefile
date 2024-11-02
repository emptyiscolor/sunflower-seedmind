.PHONY: all build copy clean

# Define the image name
IMAGE_NAME = seedcoder-artifact-builder

# Default target
all: build copy

# Build the Docker image
build:
	docker build -t $(IMAGE_NAME) .

# Create the prebuilt directory and copy artifacts from the container
copy:
	mkdir -p prebuilt
	# Run a temporary container to copy files
	docker run --name temp-container $(IMAGE_NAME) /bin/true
	# Copy the artifacts from the container to the host
	docker cp temp-container:/prebuilt/. prebuilt/
	# Remove the temporary container
	docker rm temp-container

# Clean up the prebuilt directory
clean:
	rm -rf prebuilt
