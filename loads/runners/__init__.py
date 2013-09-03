from loads.runners.distributed import DistributedRunner  # NOQA
from loads.runners.local import LocalRunner  # NOQA
from loads.runners.external import ExternalRunner  # NOQA

RUNNERS = (DistributedRunner, LocalRunner, ExternalRunner)
