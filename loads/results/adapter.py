import functools


class LoadsTestResult(object):
    """Used to make unitest calls compatible with Loads.

    This class will add to the API calls the loads_status option Loads uses.
    """
    def __init__(self, loads_status, result):
        self.result = result
        self.loads_status = loads_status

    def __getattribute__(self, name):
        klass = super(LoadsTestResult, self)
        result = klass.__getattribute__('result')
        attr = getattr(result, name)
        if name in ('startTest', 'stopTest', 'addSuccess', 'addException',
                    'addError', 'addFailure', 'incr_counter'):
            status = klass.__getattribute__('loads_status')
            return functools.partial(attr, loads_status=status)
        return attr
