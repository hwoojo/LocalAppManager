"""GTK4/libadwaita graphical interface for LocalAppManager."""

from __future__ import annotations

from pathlib import Path
import shlex
import sys
import threading
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from .doctor import diagnose, repair
from .editing import edit_app
from .errors import LocalAppError
from .external_sources import discover_gearlever
from .importers import (
    inspect_portable_folder,
    register_external_integration,
    register_file,
    register_portable_folder,
    register_python_project,
)
from .models import AppKind, AppManifest
from .paths import AppPaths
from .removal import build_removal_plan, execute_removal
from .runners import launch_app
from .storage import ManifestStore


APP_ID = "io.github.hwoo.LocalAppManager"


def _button(icon: str, tooltip: str) -> Gtk.Button:
    button = Gtk.Button(icon_name=icon)
    button.set_tooltip_text(tooltip)
    button.set_valign(Gtk.Align.CENTER)
    return button


def _command_arguments(manifest: AppManifest) -> tuple[str, ...]:
    if manifest.kind is not AppKind.PYTHON_PROJECT:
        return manifest.command[1:]
    base = 3 if manifest.python_entry_type == "module" else 2
    return manifest.command[base:]


class FormDialog(Adw.Dialog):
    def __init__(
        self, parent: Gtk.Widget, title: str, save_label: str = "등록"
    ) -> None:
        super().__init__()
        self.set_title(title)
        self.set_content_width(520)
        self.set_content_height(560)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        cancel = Gtk.Button(label="취소")
        cancel.connect("clicked", lambda *_: self.close())
        header.pack_start(cancel)
        self.save_button = Gtk.Button(label=save_label)
        self.save_button.add_css_class("suggested-action")
        header.pack_end(self.save_button)
        toolbar.add_top_bar(header)
        self.page = Adw.PreferencesPage()
        toolbar.set_content(self.page)
        self.set_child(toolbar)
        self.present(parent)

    def group(self, title: str = "") -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title=title)
        self.page.add(group)
        return group


class ManagerWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application) -> None:
        super().__init__(application=application)
        self.set_title("로컬 앱 관리자")
        self.set_default_size(780, 620)
        self.store = ManifestStore(AppPaths.from_environment())

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(
            Adw.WindowTitle(title="로컬 앱 관리자", subtitle="패키지 관리자 밖의 앱")
        )
        add_menu = Gtk.MenuButton(icon_name="list-add-symbolic", tooltip_text="앱 등록")
        add_menu.set_popover(self._build_add_popover())
        header.pack_start(add_menu)
        doctor_button = _button("emblem-system-symbolic", "상태 검사")
        doctor_button.connect("clicked", self._on_doctor)
        header.pack_end(doctor_button)
        refresh = _button("view-refresh-symbolic", "새로 고침")
        refresh.connect("clicked", lambda *_: self.refresh())
        header.pack_end(refresh)
        toolbar.add_top_bar(header)

        self.toast_overlay = Adw.ToastOverlay()
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("boxed-list")
        self.listbox.set_margin_top(18)
        self.listbox.set_margin_bottom(18)
        self.listbox.set_margin_start(18)
        self.listbox.set_margin_end(18)
        scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scrolled.set_child(self.listbox)
        self.empty = Adw.StatusPage(
            icon_name="application-x-executable-symbolic",
            title="등록된 앱이 없습니다",
            description="왼쪽 위 + 버튼으로 AppImage, 폴더, Python 프로젝트를 등록하세요.",
        )
        self.stack.add_named(scrolled, "list")
        self.stack.add_named(self.empty, "empty")
        self.toast_overlay.set_child(self.stack)
        toolbar.set_content(self.toast_overlay)
        self.set_content(toolbar)
        self.refresh()

    def _build_add_popover(self) -> Gtk.Popover:
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        items = [
            ("AppImage 또는 실행 파일", self._choose_file),
            ("Portable 앱 폴더", self._choose_portable),
            ("Python 프로젝트", self._choose_python),
            ("Gear Lever에서 가져오기", self._import_gearlever),
        ]
        for label, callback in items:
            button = Gtk.Button(label=label)
            button.set_halign(Gtk.Align.FILL)
            button.connect(
                "clicked", lambda _button, cb=callback: (popover.popdown(), cb())
            )
            box.append(button)
        popover.set_child(box)
        return popover

    def toast(self, message: str) -> None:
        self.toast_overlay.add_toast(Adw.Toast(title=message, timeout=4))

    def background(
        self, operation: Callable[[], object], success: Callable[[object], None]
    ) -> None:
        def worker() -> None:
            try:
                result = operation()
            except Exception as exc:
                GLib.idle_add(self.toast, f"실패: {exc}")
            else:
                GLib.idle_add(success, result)

        threading.Thread(target=worker, daemon=True).start()

    def refresh(self) -> None:
        while child := self.listbox.get_first_child():
            self.listbox.remove(child)
        try:
            manifests = self.store.list_manifests()
        except Exception as exc:
            self.toast(f"목록을 읽지 못했습니다: {exc}")
            manifests = ()
        for manifest in manifests:
            row = Adw.ActionRow(
                title=manifest.name,
                subtitle=f"{manifest.kind.value}  ·  {manifest.install_mode.value}",
                activatable=True,
            )
            if manifest.icon_path and Path(manifest.icon_path).exists():
                image = Gtk.Image.new_from_file(manifest.icon_path)
                image.set_pixel_size(36)
            else:
                image = Gtk.Image.new_from_icon_name(
                    "application-x-executable-symbolic"
                )
                image.set_pixel_size(32)
            row.add_prefix(image)
            run_button = _button("media-playback-start-symbolic", "실행")
            run_button.connect("clicked", lambda _b, item=manifest: self._run(item))
            row.add_suffix(run_button)
            row.connect(
                "activated", lambda _row, item=manifest: self._show_details(item)
            )
            self.listbox.append(row)
        self.stack.set_visible_child_name("list" if manifests else "empty")

    def _run(self, manifest: AppManifest) -> None:
        try:
            pid = launch_app(manifest)
        except LocalAppError as exc:
            self.toast(str(exc))
        else:
            self.toast(f"{manifest.name} 실행됨 · PID {pid}")

    def _choose_file(self) -> None:
        dialog = Gtk.FileDialog(title="AppImage 또는 실행 파일 선택")
        dialog.open(self, None, self._file_selected)

    def _file_selected(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        path = file.get_path()
        if path:
            self._file_form(Path(path))

    def _file_form(self, path: Path) -> None:
        dialog = FormDialog(self, "앱 등록")
        group = dialog.group("기본 정보")
        name = Adw.EntryRow(title="표시 이름", text=path.stem)
        group.add(name)
        managed = Adw.SwitchRow(
            title="관리 모드", subtitle="원본을 보존하고 관리 경로에 복사"
        )
        group.add(managed)
        terminal = Adw.SwitchRow(title="터미널에서 실행")
        group.add(terminal)

        def save(*_args) -> None:
            dialog.close()
            self.background(
                lambda: register_file(
                    self.store,
                    path,
                    name=name.get_text(),
                    mode="managed" if managed.get_active() else "linked",
                    terminal=terminal.get_active(),
                ),
                lambda manifest: (
                    self.refresh(),
                    self.toast(f"{manifest.name} 등록 완료"),
                ),
            )

        dialog.save_button.connect("clicked", save)

    def _choose_portable(self) -> None:
        dialog = Gtk.FileDialog(title="Portable 앱 폴더 선택")
        dialog.select_folder(self, None, self._portable_selected)

    def _portable_selected(
        self, dialog: Gtk.FileDialog, result: Gio.AsyncResult
    ) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        path = folder.get_path()
        if not path:
            return
        root = Path(path)
        try:
            inspection = inspect_portable_folder(root)
        except Exception as exc:
            self.toast(str(exc))
            return
        if not inspection.executables:
            self.toast("실행 가능한 파일을 찾지 못했습니다.")
            return
        dialog_form = FormDialog(self, "Portable 앱 등록")
        group = dialog_form.group("실행 설정")
        name = Adw.EntryRow(title="표시 이름", text=root.name)
        group.add(name)
        model = Gtk.StringList.new(
            [candidate.relative_path for candidate in inspection.executables]
        )
        executable = Adw.ComboRow(title="실행 파일", model=model)
        group.add(executable)
        managed = Adw.SwitchRow(
            title="관리 모드", subtitle="폴더 전체를 관리 경로에 복사"
        )
        group.add(managed)

        def save(*_args) -> None:
            selected = inspection.executables[executable.get_selected()].relative_path
            dialog_form.close()
            self.background(
                lambda: register_portable_folder(
                    self.store,
                    root,
                    name=name.get_text(),
                    executable=selected,
                    mode="managed" if managed.get_active() else "linked",
                ),
                lambda manifest: (
                    self.refresh(),
                    self.toast(f"{manifest.name} 등록 완료"),
                ),
            )

        dialog_form.save_button.connect("clicked", save)

    def _choose_python(self) -> None:
        dialog = Gtk.FileDialog(title="Python 프로젝트 폴더 선택")
        dialog.select_folder(self, None, self._python_selected)

    def _python_selected(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        path = folder.get_path()
        if path:
            self._python_form(Path(path))

    def _python_form(self, root: Path) -> None:
        dialog = FormDialog(self, "Python 프로젝트 등록")
        group = dialog.group("Python 실행 설정")
        name = Adw.EntryRow(title="표시 이름", text=root.name)
        group.add(name)
        guessed = root / ".venv/bin/python"
        interpreter = Adw.EntryRow(
            title="Python 인터프리터",
            text=str(guessed if guessed.exists() else Path(sys.executable)),
        )
        group.add(interpreter)
        entry_type = Adw.ComboRow(
            title="진입 방식", model=Gtk.StringList.new(["스크립트", "모듈"])
        )
        group.add(entry_type)
        entrypoint = Adw.EntryRow(title="스크립트 상대경로 또는 모듈명")
        group.add(entrypoint)
        terminal = Adw.SwitchRow(title="터미널에서 실행")
        group.add(terminal)

        def save(*_args) -> None:
            value = entrypoint.get_text().strip()
            dialog.close()
            options = (
                {"script": value}
                if entry_type.get_selected() == 0
                else {"module": value}
            )
            self.background(
                lambda: register_python_project(
                    self.store,
                    root,
                    name=name.get_text(),
                    interpreter=interpreter.get_text(),
                    terminal=terminal.get_active(),
                    **options,
                ),
                lambda manifest: (
                    self.refresh(),
                    self.toast(f"{manifest.name} 등록 완료"),
                ),
            )

        dialog.save_button.connect("clicked", save)

    def _import_gearlever(self) -> None:
        existing = {manifest.source_path for manifest in self.store.list_manifests()}

        def operation() -> list[AppManifest]:
            imported: list[AppManifest] = []
            for candidate in discover_gearlever():
                if str(candidate.source) in existing:
                    continue
                imported.append(
                    register_external_integration(
                        self.store,
                        candidate.source,
                        name=candidate.name,
                        kind=candidate.kind,
                        command=candidate.command,
                        desktop_entry=candidate.desktop_entry,
                        icon=candidate.icon,
                        terminal=candidate.terminal,
                        categories=candidate.categories,
                        startup_notify=candidate.startup_notify,
                    )
                )
            return imported

        self.background(
            operation,
            lambda imported: (
                self.refresh(),
                self.toast(f"Gear Lever에서 {len(imported)}개 앱을 가져왔습니다."),
            ),
        )

    def _show_details(self, manifest: AppManifest) -> None:
        dialog = Adw.Dialog(title=manifest.name, content_width=560, content_height=600)
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="등록 정보")
        page.add(group)
        values = [
            ("ID", manifest.app_id),
            ("종류", manifest.kind.value),
            ("방식", manifest.install_mode.value),
            ("원본", manifest.source_path),
            ("실행 명령", shlex.join(manifest.command)),
            ("작업 폴더", manifest.working_directory or "기본값"),
            (
                "Desktop 통합",
                "LocalAppManager" if manifest.integration_managed else "외부 앱 관리자",
            ),
        ]
        for title, value in values:
            group.add(Adw.ActionRow(title=title, subtitle=value))
        action_group = Adw.PreferencesGroup(title="작업")
        page.add(action_group)
        action_row = Adw.ActionRow(title="이 앱 관리")
        action_group.add(action_row)
        run = Gtk.Button(label="실행", icon_name="media-playback-start-symbolic")
        run.add_css_class("suggested-action")
        run.connect("clicked", lambda *_: self._run(manifest))
        action_row.add_suffix(run)
        if manifest.integration_managed:
            edit = Gtk.Button(label="편집", icon_name="document-edit-symbolic")
            edit.connect(
                "clicked", lambda *_: (dialog.close(), self._edit_form(manifest))
            )
            action_row.add_suffix(edit)
        remove = Gtk.Button(label="등록 제거", icon_name="user-trash-symbolic")
        remove.add_css_class("destructive-action")
        remove.connect(
            "clicked", lambda *_: (dialog.close(), self._confirm_remove(manifest))
        )
        action_row.add_suffix(remove)
        toolbar.set_content(page)
        dialog.set_child(toolbar)
        dialog.present(self)

    def _edit_form(self, manifest: AppManifest) -> None:
        dialog = FormDialog(self, f"{manifest.name} 편집", "저장")
        group = dialog.group("표시 및 실행")
        name = Adw.EntryRow(title="표시 이름", text=manifest.name)
        group.add(name)
        arguments = Adw.EntryRow(
            title="실행 인자", text=shlex.join(_command_arguments(manifest))
        )
        group.add(arguments)
        terminal = Adw.SwitchRow(title="터미널에서 실행", active=manifest.terminal)
        group.add(terminal)

        def save(*_args) -> None:
            try:
                argv = tuple(shlex.split(arguments.get_text()))
                edit_app(
                    self.store,
                    manifest.app_id,
                    name=name.get_text(),
                    arguments=argv,
                    terminal=terminal.get_active(),
                )
            except Exception as exc:
                self.toast(str(exc))
                return
            dialog.close()
            self.refresh()
            self.toast("변경사항을 저장했습니다.")

        dialog.save_button.connect("clicked", save)

    def _confirm_remove(self, manifest: AppManifest) -> None:
        try:
            plan = build_removal_plan(self.store, manifest.app_id)
        except Exception as exc:
            self.toast(str(exc))
            return
        body_lines = [f"관리 파일 {len(plan.existing_targets)}개를 제거합니다."]
        if plan.preserved_external:
            body_lines.append(
                f"원본·외부 경로 {len(plan.preserved_external)}개는 보존합니다."
            )
        if plan.unsafe_paths:
            body_lines.append("안전하지 않은 manifest 경로가 있어 제거할 수 없습니다.")
        alert = Adw.AlertDialog(
            heading=f"{manifest.name} 등록을 제거할까요?",
            body="\n".join(body_lines),
        )
        alert.add_response("cancel", "취소")
        alert.add_response("remove", "제거")
        alert.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        alert.set_default_response("cancel")
        alert.set_close_response("cancel")

        def chosen(alert_dialog: Adw.AlertDialog, result: Gio.AsyncResult) -> None:
            if alert_dialog.choose_finish(result) != "remove" or plan.unsafe_paths:
                return
            removal = execute_removal(self.store, plan)
            self.refresh()
            if removal.manifest_removed:
                self.toast(f"{manifest.name} 등록을 제거했습니다.")
            else:
                self.toast("일부 파일을 제거하지 못해 manifest를 보존했습니다.")

        alert.choose(self, None, chosen)

    def _on_doctor(self, *_args) -> None:
        report = diagnose(self.store)
        if not report.issues:
            self.toast(f"{len(report.checked)}개 앱 상태가 정상입니다.")
            return
        lines = [f"{issue.app_id}: {issue.code}" for issue in report.issues[:12]]
        alert = Adw.AlertDialog(
            heading=f"{len(report.issues)}개 문제를 찾았습니다",
            body="\n".join(lines),
        )
        alert.add_response("close", "닫기")
        alert.add_response("repair", "안전 항목 복구")
        alert.set_response_appearance("repair", Adw.ResponseAppearance.SUGGESTED)

        def chosen(alert_dialog: Adw.AlertDialog, result: Gio.AsyncResult) -> None:
            if alert_dialog.choose_finish(result) == "repair":
                repaired, failures = repair(self.store)
                self.refresh()
                self.toast(
                    f"{len(repaired)}개 앱을 복구했습니다. 실패 {len(failures)}개"
                )

        alert.choose(self, None, chosen)


class LocalAppApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS
        )

    def do_activate(self) -> None:
        window = self.get_active_window()
        if window is None:
            window = ManagerWindow(self)
        window.present()


def main(argv: list[str] | None = None) -> int:
    app = LocalAppApplication()
    return app.run(sys.argv if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
