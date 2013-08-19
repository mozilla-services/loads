_OUTPUTS = {}


def create_output(kind, test_result, args):
    if kind not in _OUTPUTS:
        raise NotImplementedError(kind)

    return _OUTPUTS[kind](test_result, args)


def register_output(klass):
    _OUTPUTS[klass.name] = klass


def output_list():
    return _OUTPUTS.values()


# register our own plugins
from loads.output.null import NullOutput
from loads.output._file import FileOutput
from loads.output.std import StdOutput
from loads.output._funkload import FunkloadOutput

for output in (NullOutput, FileOutput, StdOutput, FunkloadOutput):
    register_output(output)
