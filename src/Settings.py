import gi
import dbus
import time

from dbus.mainloop.glib import DBusGMainLoop
from .assets.emoji_list import emojis
from .lib.custom_tags import set_custom_tags, get_all_custom_tags, delete_custom_tags
from .lib.localized_tags import get_countries_list
from .utils import read_text_resource, is_wayland


gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gio, Gdk, GLib

class Settings():
    def __init__(self, application_id: str):
        builder = Gtk.Builder()
        builder.add_from_resource('/it/mijorus/smile/ui/settings.glade')
        self.window = builder.get_object('settings-window')
        self.application_id = application_id

        self.list_box = builder.get_object('preferences-listbox')
        self.custom_tags_list_box = builder.get_object('customtags-listbox')
        self.modifiers_list_box = builder.get_object('modifiers-listbox')
        self.localized_tags_list_box = builder.get_object('localized-tags-listbox')
        self.empty_list_label = Gtk.Label(label="There are no custom tags for any emoji yet; create one with <b>Alt+T</b>", use_markup=True, margin=10)

        self.settings = Gio.Settings.new('it.mijorus.smile')

        wl_not_available_text = 'Not available on Wayland'
        
        text = wl_not_available_text if is_wayland() else None
        self.create_boolean_settings_entry('Open at mouse position', 'open-on-mouse-position', text, usable=(not is_wayland()))
        self.create_boolean_settings_entry('Load on login', 'load-hidden-on-startup', 'Automatically load Smile in background for a faster launch')

        text: str = 'Minimize the window when pressing ESC\nor when selecting an emoji:\nresuming the app when minimized is faster\nbut will show up in your system tray'

        self.create_boolean_settings_entry('Minimize on exit', 'iconify-on-esc', text)
        self.create_custom_tags_list()
        self.create_modifiers_combo_boxes()
        self.create_launch_shortcut_settings_entry()
        self.create_boolean_settings_entry('Use localized tags', 'use-localized-tags', '', add_to=self.localized_tags_list_box)
        self.create_tags_locale_combo_boxes()
        self.create_boolean_settings_entry('Merge localized tags with English tags', 'merge-english-tags', 'Use both localized tags and English ones at the same time', add_to=self.localized_tags_list_box)

        if not self.settings.get_boolean('use-localized-tags'):
            self.localized_tags_list_box.set_opacity(0.7)

        self.custom_tags_entries: list[Gtk.Entry] = []
        self.settings.connect('changed', self.on_settings_changes)
        self.window.connect('destroy', self.on_window_close)

        self.window.show_all()
        self.window.present_with_time(time.time())

    def on_load_hidden_on_startup_changed(self, settings, key: str):
        value: bool = settings.get_boolean(key)

        old_autostart_file = Gio.File.new_for_path(f'{GLib.get_home_dir()}/.config/autostart/smile.autostart.desktop')
        if old_autostart_file.query_exists():
            old_autostart_file.delete()

        bus = dbus.SessionBus()
        obj = bus.get_object("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop")
        inter = dbus.Interface(obj, "org.freedesktop.portal.Background")
        res = inter.RequestBackground('', {'reason': 'Smile autostart', 'autostart': value, 'background': value, 'commandline': dbus.Array(['smile', '--start-hidden']) })

    def create_boolean_settings_entry(self, label: str, key: str, subtitle: str=None, usable: bool=True, add_to=None):
        container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, margin=10)

        # Title box
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, expand=False, margin=0, can_focus=False)
        title_box.pack_start(Gtk.Label(label=label, halign=Gtk.Align.START), True, True, 0)

        if subtitle:
            title_box.pack_end(Gtk.Label(label=f"<small>{subtitle}</small>", halign=Gtk.Align.START, use_markup=True), False, False, 0)

        container.pack_start(title_box, False, False, 0)

        # Switch
        switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.settings.bind(key, switch, 'state', Gio.SettingsBindFlags.DEFAULT)

        switch.set_sensitive(usable)

        if not usable:
            container.set_opacity(0.5)

        container.pack_end(switch, False, False, 0)

        listbox_row = Gtk.ListBoxRow(selectable=False)
        listbox_row.add(container)

        if add_to:
            add_to.add(listbox_row)
        else:
            self.list_box.add(listbox_row)

    def create_launch_shortcut_settings_entry(self):
        container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, margin=10)

        # Title box
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, expand=False, margin=0, can_focus=False)
        title_box.pack_start(Gtk.Label(label='Launch the app with a shortcut', halign=Gtk.Align.START), True, True, 0)
        title_box.pack_end(
            Gtk.Label(label=f"<small>Create a new keyboard shortcut in your\nsystem settings and paste the following code\nas a custom command</small>", halign=Gtk.Align.START, use_markup=True), False, False, 0
        )
        container.pack_start(title_box, False, False, 0)

        command_label = Gtk.Label(label=f'flatpak run {self.application_id}', selectable=True)
        container.pack_end(command_label, False, False, 0)

        listbox_row = Gtk.ListBoxRow(selectable=False)
        listbox_row.add(container)
        self.list_box.add(listbox_row)

    def create_custom_tags_list(self):
        custom_tags = get_all_custom_tags()

        rows = []
        if not len(custom_tags):
            rows.append(self.empty_list_label)
        else:
            for hexcode, config in custom_tags.items():
                if not 'tags' in config or not config['tags']:
                    continue

                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, expand=True, margin=5)

                for e, data in emojis.items():
                    if (e == hexcode):
                        label = Gtk.Label(label=data['emoji'], halign=Gtk.Align.START)
                        label.get_style_context().add_class('emoji_with_custom_tags_preferences')
                        box.pack_start( label, False, True,  5 )

                        delete_button = Gtk.Button(label="Remove")
                        delete_button.hexcode = e
                        delete_button.get_style_context().add_class('destructive-action')
                        delete_button.connect('clicked', lambda w: self.delete_tag(w.hexcode))

                        box.pack_end(delete_button, False, True,  5)

                        entry = Gtk.Entry(text=config['tags'])
                        entry.hexcode = hexcode
                        
                        box.pack_end(entry, True, True, 5 )
                        box.hexcode = e

                        break

                rows.append(box)

        
        for row in rows:
            listbox_row = Gtk.ListBoxRow(selectable=False)
            listbox_row.add(row)
            self.custom_tags_list_box.add(listbox_row)

    def delete_tag(self, hexcode: str):
        result = delete_custom_tags(hexcode)

        if result:
            for child in self.custom_tags_list_box.get_children():
                if child.get_children()[0].hexcode == hexcode:
                    self.custom_tags_list_box.remove(child)
                    break

        if (not get_all_custom_tags()) or (len(get_all_custom_tags()) == 0):
            listbox_row = Gtk.ListBoxRow(selectable=False, visible=True)
            listbox_row.add(self.empty_list_label)
            self.custom_tags_list_box.add(listbox_row)

        self.custom_tags_list_box.show_all()

    def on_settings_changes(self, settings, key: str):
        callback = getattr(self, f"on_{key.replace('-', '_')}_changed", None)

        if callback:
            callback(settings, key)

    def create_error_dialog(self, text: str):
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=text,
        )

        dialog.run()
        dialog.destroy()

    def create_modifiers_combo_boxes(self):
        skintones_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, margin=10)
        skintones_container.pack_start(Gtk.Label(label='Default skintone', halign=Gtk.Align.START), True, True, 0)

        skintones = [["", "👋"], ["1F3FB", "👋🏻"], ["1F3FC", "👋🏼"], ["1F3FD", "👋🏽"], ["1F3FE", "👋🏾"], ["1F3FF", "👋🏿"]]
        skintones_combo = Gtk.ComboBoxText()
        
        for i, j in enumerate(skintones):
            skintones_combo.append(j[0], j[1])

            if self.settings.get_string('skintone-modifier') == j[0]:
                skintones_combo.set_active(i)

        skintones_combo.connect('changed', lambda w: self.settings.set_string('skintone-modifier', w.get_active_id()))
        skintones_container.pack_end(skintones_combo, False, False, 0)

        skintones_listbox_row = Gtk.ListBoxRow(selectable=False)
        skintones_listbox_row.add(skintones_container)

        self.modifiers_list_box.add(skintones_listbox_row)

    def create_tags_locale_combo_boxes(self):
        container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, margin=10)
        container.pack_start(Gtk.Label(label='Localized tags', halign=Gtk.Align.START), True, True, 0)

        locales_combo = Gtk.ComboBoxText()
        
        i = 0
        for k, v in get_countries_list().items():
            locales_combo.append(k, v['flag'] + ' ' + k.upper())

            if self.settings.get_string('tags-locale') == k:
                locales_combo.set_active(i)

            i += 1

        locales_combo.connect('changed', lambda w: self.settings.set_string('tags-locale', w.get_active_id()))
        container.pack_end(locales_combo, False, False, 0)

        locales_picker_row = Gtk.ListBoxRow(selectable=False)
        locales_picker_row.add(container)

        self.localized_tags_list_box.add(locales_picker_row)

    def on_window_close(self, widget: Gtk.Window):
        for listbox_row in self.custom_tags_list_box.get_children():
            row = listbox_row.get_children()[0]
             
            for widget in row:
                if isinstance(widget, Gtk.Entry):
                    set_custom_tags(row.hexcode, widget.get_text())
                    break

    def on_use_localized_tags_changed(self, settings, key: str):
        if settings.get_boolean(key):
            self.localized_tags_list_box.set_opacity(1)
        else:
            self.localized_tags_list_box.set_opacity(0.7)
