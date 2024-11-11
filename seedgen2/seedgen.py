# Seed Generator 2
# Author: Wenxuan Shi <wenxuan.shi@northwestern.edu>

from seedgen2.utils.grpc import SeedD

from typing import TypeDict

# a basic structure to hold the configuration of the seed generator agent
# it should hold several things:
# 1. a instance of SeedD, to interact with the SeedD server


class SeedGenAgent:
    def __init__(self, ip_addr: str):
        self.seedd = SeedD(ip_addr)

