def test_gui_module_imports_without_creating_a_window() -> None:
    from localapp_manager import gui

    assert gui.APP_ID == "io.github.hwoo.LocalAppManager"
