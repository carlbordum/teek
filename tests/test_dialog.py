import contextlib
import os
import random
import re
import time

import pytest

import pythotk as tk


@contextlib.contextmanager
def fake_tcl_command(name, options, return_value):
    randomness = re.sub(r'\W', '', str(random.random()) + str(time.time()))
    temp_name = 'temporary_command_' + randomness
    ran = 0

    def callback(*args):
        assert len(args) % 2 == 0
        assert dict(zip(args[0::2], args[1::2])) == options

        nonlocal ran
        ran += 1
        return return_value

    fake_command = tk.create_command(callback, extra_args_type=str)

    # here comes the magic
    tk.tcl_call(None, 'rename', name, temp_name)
    tk.tcl_call(None, 'rename', fake_command, name)
    try:
        yield
    finally:
        tk.delete_command(name)
        tk.tcl_call(None, 'rename', temp_name, name)

    assert ran == 1


def test_message_boxes():
    with fake_tcl_command('tk_messageBox', {
            '-type': 'ok',
            '-icon': 'info',
            '-title': 'a',
            '-message': 'b',
            '-detail': 'c'}, 'ok'):
        assert tk.dialog.info('a', 'b', 'c') is None

    for icon in ['info', 'warning', 'error']:
        with fake_tcl_command('tk_messageBox', {
                '-type': 'ok',
                '-icon': icon,
                '-title': 'a',
                '-message': 'b'}, 'ok'):
            assert getattr(tk.dialog, icon)('a', 'b') is None

    for func, ok, icon in [(tk.dialog.ok_cancel, 'ok', 'question'),
                           (tk.dialog.retry_cancel, 'retry', 'warning')]:
        with fake_tcl_command('tk_messageBox', {
                '-type': ok + 'cancel',
                '-icon': icon,
                '-title': 'a',
                '-message': 'b'}, ok):
            assert func('a', 'b') is True

        with fake_tcl_command('tk_messageBox', {
                '-type': ok + 'cancel',
                '-icon': icon,
                '-title': 'a',
                '-message': 'b'}, 'cancel'):
            assert func('a', 'b') is False

    for string, boolean in [('yes', True), ('no', False)]:
        with fake_tcl_command('tk_messageBox', {
                '-type': 'yesno',
                '-icon': 'question',
                '-title': 'a',
                '-message': 'b'}, string):
            assert tk.dialog.yes_no('a', 'b') is boolean

    for function_name, icon in [('yes_no_cancel', 'question'),
                                ('abort_retry_ignore', 'error')]:
        for answer in function_name.split('_'):
            with fake_tcl_command('tk_messageBox', {
                    '-type': function_name.replace('_', ''),
                    '-icon': icon,
                    '-title': 'a',
                    '-message': 'b'}, answer):
                assert getattr(tk.dialog, function_name)('a', 'b') == answer


def test_color():
    with fake_tcl_command('tk_chooseColor', {}, '#ffffff'):
        assert tk.dialog.color() == tk.Color('white')

    window = tk.Window()
    with fake_tcl_command('tk_chooseColor', {
            '-title': 'toot',
            '-initialcolor': tk.Color('maroon').to_tcl(),
            '-parent': window.toplevel.to_tcl()}, '#ffffff'):
        assert tk.dialog.color(
            initialcolor=tk.Color('maroon'),
            parent=window,
            title='toot',
        ) == tk.Color('white')

    with fake_tcl_command('tk_chooseColor', {}, ''):
        assert tk.dialog.color() is None


def test_open_file():
    window = tk.Window()

    def check(func, python_return, tcl_command, tcl_return, tcl_options=None):
        tcl_options = {} if tcl_options is None else tcl_options.copy()

        with fake_tcl_command(tcl_command, tcl_options, tcl_return):
            assert func() == python_return

        tcl_options['-parent'] = window.toplevel.to_tcl()
        with fake_tcl_command(tcl_command, tcl_options, tcl_return):
            assert func(parent=window) == python_return

    # aa = absolute a
    aa = os.path.abspath('a')
    ab = os.path.abspath('b')

    check(tk.dialog.open_file, None, 'tk_getOpenFile', '')
    check(tk.dialog.open_file, aa, 'tk_getOpenFile', 'a')
    check(tk.dialog.open_multiple_files, [], 'tk_getOpenFile', '',
          {'-multiple': '1'})
    check(tk.dialog.open_multiple_files, [aa, ab], 'tk_getOpenFile',
          ['a', 'b'], {'-multiple': '1'})
    check(tk.dialog.save_file, None, 'tk_getSaveFile', '')
    check(tk.dialog.save_file, aa, 'tk_getSaveFile', 'a')
    check(tk.dialog.directory, None, 'tk_chooseDirectory', '')
    check(tk.dialog.directory, aa, 'tk_chooseDirectory', 'a')

    with pytest.raises(TypeError) as error:
        tk.dialog.open_file(multiple=True)
    assert 'open_multiple_files()' in str(error.value)