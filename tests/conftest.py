import contextlib

import pytest

import teek as tk


# https://docs.pytest.org/en/latest/doctest.html#the-doctest-namespace-fixture
@pytest.fixture(autouse=True)
def add_tk(doctest_namespace):
    doctest_namespace['tk'] = tk


# the following url is on 2 lines because pep8 line length
#
# https://docs.pytest.org/en/latest/example/simple.html#control-skipping-of-tes
# ts-according-to-command-line-option
def pytest_addoption(parser):
    parser.addoption(
        "--skipslow", action="store_true", default=False, help="run slow tests"
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--skipslow"):
        skip_slow = pytest.mark.skip(reason="--skipslow was used")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)


@pytest.fixture
def deinit_threads():
    """Make sure that init_threads() has not been called when test completes.

    If you have a test like this...

        def test_tootie():
            tk.init_threads()

    ...the test will cause problems for any other tests that also call
    init_threads(), because it can't be called twice. Using this fixture in
    test_tootie() would fix that problem.
    """
    yield
    tk.after_idle(tk.quit)
    tk.run()


@pytest.fixture
def handy_callback():
    def handy_callback_decorator(function):
        def result(*args, **kwargs):
            return_value = function(*args, **kwargs)
            result.ran += 1
            return return_value

        result.ran = 0
        result.ran_once = (lambda: result.ran == 1)
        return result

    return handy_callback_decorator


@pytest.fixture
def check_config_types():
    def checker(config, debug_info):
        # this converts all values to their types, and this probably fails if
        # the types are wrong
        dict(config)

        # were there keys that defaulted to str?
        known_keys = config._types.keys() | config._special.keys()
        for key in (config.keys() - known_keys):
            print('\ncheck_config_types', debug_info, 'warning: type of',
                  key, 'was guessed to be str')

    return checker


# this is tested in test_widgets.py
@pytest.fixture
def all_widgets():
    window = tk.Window()
    return [
        tk.Button(window),
        tk.Checkbutton(window),
        tk.Combobox(window),
        tk.Entry(window),
        tk.Frame(window),
        tk.Label(window),
        tk.LabelFrame(window),
        tk.Notebook(window),
        tk.Menu(),
        tk.Progressbar(window),
        tk.Scrollbar(window),
        tk.Separator(window),
        tk.Spinbox(window),
        tk.Text(window),
        tk.Toplevel(),
        window,
    ]


@pytest.fixture
def fake_command():
    @contextlib.contextmanager
    def faker(name, return_value=None):
        called = []

        def command_func(*args):
            called.append(list(args))
            return return_value

        fake = tk.create_command(command_func, [], extra_args_type=str)

        tk.tcl_call(None, 'rename', name, name + '_real')
        try:
            tk.tcl_call(None, 'rename', fake, name)
            yield called
        finally:
            try:
                tk.delete_command(name)
            except tk.TclError:
                pass
            tk.tcl_call(None, 'rename', name + '_real', name)

    return faker
