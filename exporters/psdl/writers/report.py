# Where the writers report their warnings and errors: the ExportReport module of km2 City Builder when they run in its
# exporter (Files/python is on the path then), otherwise standalone tools print their messages.
# The keyword arguments are the ones of ExportReport (element, kind, code, position, details, overlay).
import contextlib
import traceback

try:
    import ExportReport as _report
except ImportError:
    _report = None


def _supported(kwargs):
    # without the arguments that the ExportReport of an older program doesn't take (overlay)
    if _report is None or 'overlay' not in kwargs:
        return kwargs
    import inspect
    if 'overlay' in inspect.signature(_report.report).parameters:
        return kwargs
    return {k: v for k, v in kwargs.items() if k != 'overlay'}


# whether the errors are collected (the export goes on after one, and fails at the end) instead of raised
def collecting():
    return _report is not None


# runs the block of the with statement: an exception is reported as an error when the errors are collected,
# raised otherwise
@contextlib.contextmanager
def guarded(message, **kwargs):
    try:
        yield
    except Exception:
        if not collecting():
            raise
        _report.exception(message, **kwargs)


def warning(message, **kwargs):
    if _report is not None:
        _report.warning(message, **_supported(kwargs))
    else:
        print("Warning: " + message)


def error(message, **kwargs):
    if _report is not None:
        _report.error(message, **_supported(kwargs))
    else:
        print("Error: " + message)


def info(message, **kwargs):
    if _report is not None:
        _report.info(message, **_supported(kwargs))
    else:
        print(message)


# the exception being handled, as an error
def exception(message=None, **kwargs):
    if _report is not None:
        _report.exception(message, **kwargs)
    else:
        print("Error: " + (message or ""))
        traceback.print_exc()


def has_errors():
    return _report is not None and _report.has_errors()


# the name of the element of an original_name property (without the part, e.g. "Road 3 [shoulder]" -> "Road 3")
def element_name(original_name):
    if not original_name:
        return None
    name = str(original_name)
    while name.endswith("]") and " [" in name:
        name = name[:name.rindex(" [")]
    return name
