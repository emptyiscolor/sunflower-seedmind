GOCMD = go
GOBUILD = $(GOCMD) build -buildvcs=false
GOCLEAN = $(GOCMD) clean
GOGET = $(GOCMD) get

BINARY_NAME = seedgen-injected
BUILD_DIR = bin

all: deps build

deps:
	$(GOGET) ./...

build: seedgen-injected

seedgen-injected:
	CGO_ENABLED=0 $(GOBUILD) -o $(BUILD_DIR)/$(BINARY_NAME) ./cmd/seedgen-injected

clean:
	$(GOCLEAN)
	rm -rf $(BUILD_DIR)