import teek as tk

import pytest


def test_item_types():
    menu = tk.Menu([
        tk.MenuItem("Click me", print),
        tk.MenuItem(),     # separator
        tk.MenuItem("Check me", tk.BooleanVar()),
        tk.MenuItem("Choose me or one of my friends", tk.StringVar(), "me"),
        tk.MenuItem("Submenu", [
            tk.MenuItem("Click here", print)
        ]),
        tk.MenuItem("Different kind of submenu", tk.Menu([
            tk.MenuItem("Click me", print),
        ])),
    ])
    assert [item.type for item in menu] == [
        'command', 'separator', 'checkbutton', 'radiobutton', 'cascade',
        'cascade']

    for submenu_item in (menu[-2], menu[-1]):
        assert submenu_item.config['menu'][0].type == 'command'

    with pytest.raises(TypeError, match=r'^expected .* arguments.*$'):
        tk.MenuItem("adding only 1 argument is wrong")


def test_menuitem_objects():
    item = tk.MenuItem("Click me", print, activeforeground=tk.Color(1, 2, 3))
    assert repr(item) == (
        "<MenuItem('Click me', <built-in function print>): "
        "type='command', not added to a menu yet>")

    menu = tk.Menu([item])
    assert repr(item) == (
        "<MenuItem('Click me', <built-in function print>): "
        "type='command', added to a menu>")

    # the menu should cache the item
    assert menu[0] is item
    assert menu[0] is menu[0]


def test_repr():
    menu = tk.Menu([
        tk.MenuItem("Click me", print),
        tk.MenuItem("Check me", tk.BooleanVar()),
    ])
    assert repr(menu) == '<teek.Menu widget: contains 2 items>'


def test_must_be_menuitem_object():
    with pytest.raises(TypeError) as error:
        tk.Menu().append(("Click me", print))
    assert str(error.value) == (
        "expected a MenuItem, got ('Click me', <built-in function print>)")


def test_not_added_to_menu_yet():
    menu = tk.Menu()
    item = tk.MenuItem("Click me", print)

    check = pytest.raises(RuntimeError,
                          match=r".*hasn't been added to a Menu.*")
    with check:
        item.config['label']
    menu.append(item)
    assert item.config['label'] == "Click me"
    assert menu.pop() is item
    with check:
        item.config['label']


def test_added_to_2_menus_at_the_same_time():
    item = tk.MenuItem("Click me", print)
    menu = tk.Menu()
    menu.append(item)

    check = pytest.raises(RuntimeError, match=(
        r'^cannot add a MenuItem to two different menus '
        r'or twice to the same menu$'))
    with check:
        menu.append(item)
    with check:
        tk.Menu().append(item)


def test_destroying_deletes_commands(handy_callback):
    @handy_callback
    def callback_func():
        pass

    menu = tk.Menu([
        tk.MenuItem("Click me", callback_func),
    ])
    command_string = tk.tcl_call(str, menu, 'entrycget', 0, '-command')
    tk.tcl_call(None, command_string)
    assert callback_func.ran_once()

    menu.destroy()
    with pytest.raises(tk.TclError):
        tk.tcl_call(None, command_string)


def test_config(check_config_types):
    boolean_var = tk.BooleanVar()
    string_var = tk.StringVar()
    menu = tk.Menu([
        tk.MenuItem("Click me", print),
        tk.MenuItem("Check me", boolean_var),
        tk.MenuItem("Choice A", string_var, "a"),
        tk.MenuItem("Choice B", string_var, "b"),
        tk.MenuItem("Choice C", string_var, "c"),
        tk.MenuItem(),
        tk.MenuItem("Submenu", []),
    ])

    for item in menu:
        check_config_types(item.config, 'menu %s item' % item.type)

    assert isinstance(menu[0].config['command'], tk.Callback)
    menu[0].config['command'].disconnect(print)     # fails if not connected

    assert isinstance(menu[1].config['variable'], tk.BooleanVar)
    assert menu[1].config['variable'] == boolean_var

    for index in (2, 3, 4):
        assert isinstance(menu[index].config['variable'], tk.StringVar)
        assert menu[index].config['variable'] == string_var


def test_list_like_behaviour():
    menu = tk.Menu()
    menu.append(tk.MenuItem("Click me", print))
    assert len(menu) == 1
    assert menu[0].config['label'] == "Click me"

    menu[-1] = tk.MenuItem("No, click me instead", print)
    assert len(menu) == 1
    assert menu[0].config['label'] == "No, click me instead"

    menu.insert(123, tk.MenuItem("Last item", print))
    assert menu[-1].config['label'] == 'Last item'


def test_slicing_not_supported_errors():
    check = pytest.raises(TypeError,
                          match=r'^slicing a Menu widget is not supported$')

    menu = tk.Menu()
    with check:
        menu[:]
    with check:
        menu[:] = []
    with check:
        del menu[:]


def test_readding_to_menus():
    menu1 = tk.Menu()
    menu2 = tk.Menu()

    def lengths():
        return (len(menu1), len(menu2))

    item = tk.MenuItem()
    assert lengths() == (0, 0)

    menu1.append(item)
    assert lengths() == (1, 0)
    menu1.remove(item)
    assert lengths() == (0, 0)

    menu1.append(item)
    assert lengths() == (1, 0)
    menu1.remove(item)
    assert lengths() == (0, 0)

    menu2.append(item)
    assert lengths() == (0, 1)
    menu2.remove(item)
    assert lengths() == (0, 0)

    menu1.append(item)
    assert lengths() == (1, 0)
    menu1.remove(item)
    assert lengths() == (0, 0)


def test_indexes_dont_mess_up_ever_like_srsly_not_ever_never():
    menu = tk.Menu()

    def check():
        assert [item._index for item in menu] == list(range(len(menu)))

    menu.append(tk.MenuItem())
    check()
    menu.append(tk.MenuItem())
    check()
    menu.extend([tk.MenuItem(), tk.MenuItem(), tk.MenuItem(), tk.MenuItem()])
    check()
    menu.pop()
    check()
    menu.pop(-2)
    check()
    del menu[0]
    check()
    menu.insert(1, tk.MenuItem())
    check()
    menu[1] = tk.MenuItem()
    check()
    menu.clear()
    check()


def test_popup():
    menu = tk.Menu()
    assert not menu.winfo_ismapped()
    menu.popup(123, 456)
    assert menu.winfo_ismapped()

    menu2 = tk.Menu([tk.MenuItem("Click me", print)])
    menu2.popup(123, 456, menu2[0])
    assert menu2.winfo_ismapped()
