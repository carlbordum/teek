import teek as tk


window = tk.Window()

tk.Label(window, "asd asd").pack()
tk.Separator(window).pack(fill='x')
tk.Label(window, "moar asd").pack()

window.on_delete_window.connect(tk.quit)
tk.run()
