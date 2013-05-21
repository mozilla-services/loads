_OUTPUTS = {}


def create_output(kind, args):
    if kind not in _OUTPUTS:
        raise NotImplementedError(kind)

    return _OUTPUTS[kind](args)


def register_output(klass):
    _OUTPUTS[klass.name] = klass


def output_list():
    return _OUTPUTS.values()


# register our own plugins
from null import NullOutput
from _file import FileOutput
from std import StdOutput

for output in (NullOutput, FileOutput, StdOutput):
    register_output(output)
