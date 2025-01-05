# Compiler and flags
CXX := clang++
CXXFLAGS := -std=c++17 -Wall -Wextra -Werror -pedantic
CXXFLAGS += -I$(shell llvm-config --includedir)
CXXFLAGS += -Iinclude

# Debug/Release flags
ifdef DEBUG
    CXXFLAGS += -g -O0 -DDEBUG
else
    CXXFLAGS += -O3 -DNDEBUG
endif

# Linker flags
LDFLAGS := -lclang

# Directories
SRC_DIR := src
INCLUDE_DIR := include
BUILD_DIR := build
OBJ_DIR := $(BUILD_DIR)/obj

# Source files
SRCS := $(wildcard $(SRC_DIR)/*.cpp)
SRCS += main.cpp

# Object files
OBJS := $(SRCS:%.cpp=$(OBJ_DIR)/%.o)

# Main target
TARGET := $(BUILD_DIR)/extractor

# Targets
.PHONY: all clean debug release

all: release

debug: CXXFLAGS += -g -O0 -DDEBUG
debug: $(TARGET)

release: CXXFLAGS += -O3 -DNDEBUG
release: $(TARGET)

$(TARGET): $(OBJS) | $(BUILD_DIR)
	@echo "Linking $@..."
	@$(CXX) $(OBJS) -o $@ $(LDFLAGS)

# Pattern rule for object files
$(OBJ_DIR)/%.o: %.cpp | $(OBJ_DIR) $(OBJ_DIR)/$(SRC_DIR)
	@echo "Compiling $<..."
	@$(CXX) $(CXXFLAGS) -c $< -o $@

# Create build directories
$(BUILD_DIR) $(OBJ_DIR) $(OBJ_DIR)/$(SRC_DIR):
	@mkdir -p $@

clean:
	@echo "Cleaning..."
	@rm -rf $(BUILD_DIR)

# Include dependencies
-include $(OBJS:.o=.d)

# Generate dependency files
$(OBJ_DIR)/%.d: %.cpp | $(OBJ_DIR) $(OBJ_DIR)/$(SRC_DIR)
	@$(CXX) $(CXXFLAGS) -MM -MT '$(OBJ_DIR)/$*.o' $< > $@

# Help target
help:
	@echo "Available targets:"
	@echo "  all      - Build release version (default)"
	@echo "  debug    - Build with debug symbols"
	@echo "  release  - Build optimized version"
	@echo "  clean    - Remove build files"
	@echo "  help     - Show this help message"
	@echo ""
	@echo "Usage examples:"
	@echo "  make              # Build release version"
	@echo "  make debug        # Build debug version"
	@echo "  make clean        # Clean build files"
