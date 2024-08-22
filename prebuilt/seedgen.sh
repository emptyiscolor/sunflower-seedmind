#!/bin/bash

# This script is used to run inside OSS Fuzz container

# First, we need to compile the project
compile

# Then, run the seedgen-injected binary
/seedgen-injected