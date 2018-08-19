import collections
import functools
import itertools
import numbers
import queue
import sys
import threading
import traceback
import _tkinter

import pythotk
from pythotk import _structures

_flatten = itertools.chain.from_iterable


def raise_pythotk_tclerror(func):
    @functools.wraps(func)
    def result(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except _tkinter.TclError as e:
            raise (pythotk.TclError(str(e))
                   .with_traceback(e.__traceback__)) from None

    return result


counts = collections.defaultdict(lambda: itertools.count(1))
on_quit = _structures.Callback()


# because readability is good
# TODO: is there something like this in e.g. concurrent.futures?
class _Future:

    def __init__(self):
        self._value = None
        self._error = None
        self._event = threading.Event()
        self._success = None

    def set_value(self, value):
        self._value = value
        self._success = True
        self._event.set()

    def set_error(self, exc):
        self._error = exc
        self._success = False
        self._event.set()

    def get_value(self):
        self._event.wait()
        assert self._success is not None
        if not self._success:
            raise self._error
        return self._value


class _TclInterpreter:

    def __init__(self):
        assert threading.current_thread() is threading.main_thread()

        self._init_threads_called = False

        # tkinter does this :D i have no idea what each argument means
        self._app = _tkinter.create(None, sys.argv[0], 'Tk', 1, 1, 1, 0, None)

        self._app.call('wm', 'withdraw', '.')
        self._app.call('package', 'require', 'tile')

        # when call or eval is called from some other thread than the main
        # thread, a tuple like this is added to this queue:
        #
        #    (func, args, kwargs, future)
        #
        # func is a function that MUST be called from main thread
        # args and kwargs are arguments for func
        # future will be set when the function has been called
        #
        # the function is called from Tk's event loop
        self._call_queue = queue.Queue()

    @raise_pythotk_tclerror
    def init_threads(self, poll_interval_ms=50):
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError(
                "init_threads() must be called from main thread")

        # there is a race condition here, but if it actually creates problems,
        # you are doing something very wrong
        if self._init_threads_called:
            raise RuntimeError("init_threads() was called twice")

        # hard-coded name is ok because there is only one of these in each
        # Tcl interpreter
        poller_tcl_command = 'pythotk_init_threads_queue_poller'

        after_id = None

        @raise_pythotk_tclerror
        def poller():
            nonlocal after_id

            while True:
                try:
                    item = self._call_queue.get(block=False)
                except queue.Empty:
                    break

                func, args, kwargs, future = item
                try:
                    value = func(*args, **kwargs)
                except Exception as e:
                    future.set_error(e)
                else:
                    future.set_value(value)

            after_id = self._app.call(
                'after', poll_interval_ms, 'pythotk_init_threads_queue_poller')

        self._app.createcommand(poller_tcl_command, poller)
        on_quit.connect(
            lambda: None if after_id is None else self._app.call(
                'after', 'cancel', after_id))

        poller()
        self._init_threads_called = True

    def call_thread_safely(self, non_threadsafe_func, args=(), kwargs=None):
        if kwargs is None:
            kwargs = {}

        if threading.current_thread() is threading.main_thread():
            return non_threadsafe_func(*args, **kwargs)

        if not self._init_threads_called:
            raise RuntimeError("init_threads() wasn't called")

        future = _Future()
        self._call_queue.put((non_threadsafe_func, args, kwargs, future))
        return future.get_value()

    # self._app must be accessed from the main thread, and this class provides
    # methods for calling it thread-safely

    @raise_pythotk_tclerror
    def run(self):
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("run() must be called from main thread")

        # no idea what the 0 does, tkinter calls it like this
        self._app.mainloop(0)

    @raise_pythotk_tclerror
    def getboolean(self, arg):
        return self.call_thread_safely(self._app.getboolean, [arg])

    # _tkinter returns tuples when tcl represents something as a
    # list internally, but this forces it to string
    @raise_pythotk_tclerror
    def get_string(self, from_underscore_tkinter):
        if isinstance(from_underscore_tkinter, str):
            return from_underscore_tkinter
        if isinstance(from_underscore_tkinter, _tkinter.Tcl_Obj):
            return from_underscore_tkinter.string

        # it's probably a tuple because _tkinter returns tuples when tcl
        # represents something as a list internally, this forces tcl to
        # represent it as a string instead
        concatted = self.call_thread_safely(
            self._app.call, ['concat', 'junk', from_underscore_tkinter])
        junk, result = concatted.split(maxsplit=1)
        assert junk == 'junk'
        return result

    @raise_pythotk_tclerror
    def splitlist(self, value):
        return self.call_thread_safely(self._app.splitlist, [value])

    @raise_pythotk_tclerror
    def call(self, *args):
        return self.call_thread_safely(self._app.call, args)

    @raise_pythotk_tclerror
    def eval(self, code):
        return self.call_thread_safely(self._app.eval, [code])

    @raise_pythotk_tclerror
    def createcommand(self, name, func):
        return self.call_thread_safely(self._app.createcommand, [name, func])

    @raise_pythotk_tclerror
    def deletecommand(self, name):
        return self.call_thread_safely(self._app.deletecommand, [name])


# a global _TclInterpreter instance
_interp = None


# these are the only functions that access _interp directly
def _get_interp():
    global _interp

    if _interp is None:
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("init_threads() wasn't called")
        _interp = _TclInterpreter()
    return _interp


def quit():
    """Stop the event loop and destroy all widgets.

    This function calls ``destroy .`` in Tcl, and that's documented in
    :man:`destroy(3tk)`. Note that this function does not tell Python to quit;
    only pythotk quits, so you can do this::

        import pythotk as tk

        window = tk.Window()
        tk.Button(window, "Quit", tk.quit).pack()
        tk.run()
        print("Still alive")

    If you click the button, it interrupts ``tk.run()`` and the print runs.

    .. note::
        Closing a :class:`.Window` with the X button in the corner calls
        ``tk.quit`` by default. If you don't want that, you can prevent it like
        this::

            window.on_delete_window.disconnect(tk.quit)

        See :class:`.Toplevel` for details.
    """
    global _interp

    if threading.current_thread() is not threading.main_thread():
        # TODO: allow quitting from other threads or document this
        raise RuntimeError("can only quit from main thread")

    if _interp is not None:
        on_quit.run()
        _interp.call('destroy', '.')
        _interp = None


def run():
    """Runs the event loop until :func:`~pythotk.quit` is called."""
    _get_interp().run()


@raise_pythotk_tclerror
def init_threads(poll_interval_ms=50):
    """Allow using pythotk from other threads than the main thread.

    This is implemented with a queue. This function starts an
    :ref:`after callback <after-cb>` that checks for new messages in the queue
    every 50 milliseconds (that is, 20 times per second), and when another
    thread calls a pythotk function that does a :ref:`Tcl call <tcl-calls>`,
    the information required for making the Tcl call is put to the queue and
    the Tcl call is done by the after callback.

    .. note::
        After callbacks don't work without the event loop, so make sure to run
        the event loop with :func:`.run` after calling :func:`.init_threads`.

    ``poll_interval_ms`` can be given to specify a different interval than 50
    milliseconds.

    When a Tcl call is done from another thread, that thread blocks until the
    after callback has handled it, which is slow. If this is a problem, there
    are two things you can do:

    * Use a smaller ``poll_interval_ms``. Watch your CPU usage though; if you
      make ``poll_interval_ms`` too small, you might get 100% CPU usage when
      your program is doing nothing.
    * Try to rewrite the program so that it does less pythotk stuff in threads.
    """
    _get_interp().init_threads()


def needs_main_thread(func):
    """Functions decorated with this run in the main thread.

    If the function is invoked from a different thread than the main thread,
    the queue stuff is used for running it in the main thread.

    If you have many functions decorated with this, let's say ``func1``,
    ``func2`` and ``func3``, **this code is bad**::

        def func123():
            func1()
            func2()
            func3()

    If called from a thread different from the main thread, ``func123()`` will
    add a separate item to the queue for each of the three functions. If you
    do this instead...
    ::

        @needs_main_thread
        def func123():
            func1()
            func2()
            func3()

    ...there will be only 1 item in the queue for every ``func123()`` call
    because ``func1()``, ``func2()`` and ``func3()`` will already be invoked
    from the main thread, and they don't need the queue stuff anymore. This
    makes things a lot faster when the function is called from a thread.

    This is why pythotk functions that do multiple Tcl calls should be
    decorated with this decorator. Note that call and eval are also decorated
    with this, so decorating functions that call and eval is purely an
    optimization.
    """
    @functools.wraps(func)
    def safe(*args, **kwargs):
        return _get_interp().call_thread_safely(func, args, kwargs)

    return safe


def to_tcl(value):
    if hasattr(value, 'to_tcl'):    # duck-typing ftw
        return value.to_tcl()

    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, collections.abc.Mapping):
        return tuple(map(to_tcl, _flatten(value.items())))
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, numbers.Real):    # after bool check, bools are ints
        return str(value)

    # assume it's some kind of iterable, this must be after the Mapping
    # and str stuff above
    return tuple(map(to_tcl, value))


def _pairs(sequence):
    assert len(sequence) % 2 == 0, "cannot divide %r into pairs" % (sequence,)
    return zip(sequence[0::2], sequence[1::2])


def from_tcl(type_spec, value):
    if type_spec is None:
        return None

    if type_spec is str:
        return _get_interp().get_string(value)

    if type_spec is bool:
        if not from_tcl(str, value):
            # '' is not a valid bool, but this is usually what was intended
            # TODO: document this
            return None

        try:
            return _get_interp().getboolean(value)
        except pythotk.TclError as e:
            raise ValueError(str(e)).with_traceback(e.__traceback__) from None

    if isinstance(type_spec, type):     # it's a class
        if issubclass(type_spec, numbers.Real):     # must be after bool check
            return type_spec(from_tcl(str, value))

        if hasattr(type_spec, 'from_tcl'):
            string = from_tcl(str, value)

            # the empty string is the None value in tcl
            if not string:
                return None

            return type_spec.from_tcl(string)

    elif isinstance(type_spec, (list, tuple, dict)):
        items = _get_interp().splitlist(value)

        if isinstance(type_spec, list):
            # [int] -> [1, 2, 3]
            (item_spec,) = type_spec
            return [from_tcl(item_spec, item) for item in items]

        if isinstance(type_spec, tuple):
            # (int, str) -> (1, 'hello')
            if len(type_spec) != len(items):
                raise ValueError("expected a sequence of %d items, got %r"
                                 % (len(type_spec), list(items)))
            return tuple(map(from_tcl, type_spec, items))

        if isinstance(type_spec, dict):
            # {'a': int, 'b': str} -> {'a': 1, 'b': 'lol', 'c': 'str assumed'}
            result = {}
            for key, value in _pairs(items):
                key = from_tcl(str, key)
                result[key] = from_tcl(type_spec.get(key, str), value)
            return result

        raise RuntimeError("this should never happen")      # pragma: no cover

    raise TypeError("unknown type specification " + repr(type_spec))


@raise_pythotk_tclerror
def call(returntype, command, *arguments):
    """Call a Tcl command.

    The arguments are passed correctly, even if they contain spaces:

    >>> tk.eval(None, 'puts "hello world thing"')  # 1 arguments to puts \
        # doctest: +SKIP
    hello world thing
    >>> message = 'hello world thing'
    >>> tk.eval(None, 'puts %s' % message)  # 3 arguments to puts, tcl error
    Traceback (most recent call last):
        ...
    pythotk.TclError: wrong # args: should be "puts ?-nonewline? ?channelId? \
string"
    >>> tk.call(None, 'puts', message)   # 1 argument to puts  # doctest: +SKIP
    hello world thing
    """
    result = _get_interp().call(tuple(map(to_tcl, (command,) + arguments)))
    return from_tcl(returntype, result)


@raise_pythotk_tclerror
def eval(returntype, code):
    """Run a string of Tcl code.

    >>> eval(None, 'proc add {a b} { return [expr $a + $b] }')
    >>> eval(int, 'add 1 2')
    3
    >>> call(int, 'add', 1, 2)      # usually this is better, see below
    3
    """
    result = _get_interp().eval(code)
    return from_tcl(returntype, result)


# TODO: add support for passing arguments!
@needs_main_thread
@raise_pythotk_tclerror
def create_command(func, args=(), kwargs=None, stack_info=''):
    """Create a Tcl command that runs ``func(*args, **kwargs)``.

    Created commands should be deleted with :func:`.delete_command` when they
    are no longer needed.

    The Tcl command's name is returned as a string. The return value is
    converted to string for Tcl similarly as with :func:`call`.

    If the function raises an exception, a traceback will be printed
    with *stack_info* right after the "Traceback (bla bla bla)" line.
    However, the Tcl command returns an empty string on errors and does
    *not* raise a Tcl error. Be sure to return a non-empty value on
    success if you want to do error handling in Tcl code.

    .. seealso::
        Use :func:`traceback.format_stack` to get a *stack_info* string.
    """
    if kwargs is None:
        kwargs = {}

    def real_func():
        try:
            return to_tcl(func(*args, **kwargs))
        except Exception as e:
            traceback_blabla, rest = traceback.format_exc().split('\n', 1)
            print(traceback_blabla, file=sys.stderr)
            print(stack_info + rest, end='', file=sys.stderr)
            return ''

    name = 'pythotk_command_%d' % next(counts['commands'])
    _get_interp().createcommand(name, real_func)
    return name


@needs_main_thread
@raise_pythotk_tclerror
def delete_command(name):
    """Delete a Tcl command by name.

    You can delete commands returned from :func:`create_command` to
    avoid memory leaks.
    """
    _get_interp().deletecommand(name)
