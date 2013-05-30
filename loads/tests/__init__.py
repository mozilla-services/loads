import sys
import StringIO


def hush(func):
    """Make the passed function silent."""
    def _silent(*args, **kw):
        old = sys.stdout
        sys.stdout = StringIO.StringIO()
        try:
            return func(*args, **kw)
        finally:
            sys.stdout = old
    return _silent
