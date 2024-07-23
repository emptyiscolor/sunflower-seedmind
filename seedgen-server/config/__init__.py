import os

CP_ROOT = os.getenv("AIXCC_CP_ROOT")
CRS_SCRATCH = os.getenv("AIXCC_CRS_SCRATCH_SPACE")

# Mounting Configurations (global)
SEEDGEN_PATH = f"{CRS_SCRATCH}/fuzzing/seedgen"
ARGUS_PATH = f"{CRS_SCRATCH}/fuzzing/seedgen/argus"
BANDLD_PATH = f"{CRS_SCRATCH}/fuzzing/seedgen/bandld"
SEEDGEN_INJECTED_PATH = f"{CRS_SCRATCH}/fuzzing/seedgen/seedgen-injected"
SEEDPOOL_PATH = f"{CRS_SCRATCH}/fuzzing/seedgen/seedpool"

# Injected Service Name
INJECTED_SERVICE_NAME="seedgen-injected"

# GRPC Server Config
MAX_RETRIES = 10
RETRY_INTERVAL = 10