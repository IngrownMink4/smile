# main.py
#
# Copyright 2021 Lorenzo Paderi
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import gi
import time
import re

from .assets.emoji_list import emojis, emoji_categories
from .ShortcutsWindow import ShortcutsWindow
from .components.CustomTagEntry import CustomTagEntry
from .components.SkintoneSelector import SkintoneSelector
from .components.FlowBoxChild import FlowBoxChild
from .components.EmojiButton import EmojiButton
from .lib.custom_tags import get_custom_tags
from .lib.localized_tags import get_localized_tags
from .lib.emoji_history import increament_emoji_usage_counter, get_history
from .utils import tag_list_contains, is_wayland

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Gio, Gdk, Adw  # noqa


class Picker(Gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(title="Smile", resizable=True, *args, **kwargs)
        self.set_default_size(350, 350)

        self.event_controller_keys = Gtk.EventControllerKey()
        self.event_controller_keys_lc = Gtk.EventControllerLegacy()
        self.event_controller_keys.connect('key-pressed', self.handle_window_key_press)

        self.add_controller(self.event_controller_keys)

        self.settings: Gio.Settings = Gio.Settings.new('it.mijorus.smile')
        self.settings.connect('changed::skintone-modifier', self.update_emoji_skintones)

        self.emoji_grid_col_n = 5
        self.emoji_grid_first_row = []

        self.selected_category_index = 0
        self.selected_category = 'smileys-emotion'
        self.query: str = None
        self.selection: list[str] = []
        self.selected_buttons: list[EmojiButton] = []
        self.history_size = 0

        self.clipboard = Gdk.Display.get_default().get_clipboard()

        # Create the emoji list and category picker
        self.categories_count = 0
        scrolled = Gtk.ScrolledWindow(min_content_height=350, propagate_natural_height=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.viewport_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['viewport'])

        self.list_tip_revealer = Gtk.Revealer(reveal_child=False)
        self.list_tip_label = Gtk.Label(label='', opacity=0.7, justify=Gtk.Justification.CENTER)
        self.list_tip_revealer.set_child(self.list_tip_label)

        self.emoji_list_widgets: list[FlowBoxChild] = []
        self.emoji_list = self.create_emoji_list()
        self.category_count = 0  # will be set in create_category_picker()
        self.category_picker_widgets: list[Gtk.Button] = []
        self.category_picker = self.create_category_picker()
        scrolled.set_child(self.emoji_list)

        self.viewport_box.append(self.list_tip_revealer)
        self.viewport_box.append(scrolled)
        self.viewport_box.append(self.category_picker)

        # Create an header bar
        self.header_bar = Adw.HeaderBar(title_widget=Gtk.Box())
        self.menu_button = self.create_menu_button()
        self.header_bar.pack_end(self.menu_button)

        # Create search entry
        self.search_entry = Gtk.SearchEntry(hexpand=True, width_request=200)
        self.search_entry.connect('search_changed', self.search_emoji)
        self.search_entry.grab_focus()

        self.header_bar.pack_start(self.search_entry)
        self.set_titlebar(self.header_bar)

        self.shortcut_window: ShortcutsWindow = None
        self.shift_key_pressed = False

        # Display custom tags at the top of the list when searching
        # This variable the status of the sorted status
        self.list_was_sorted = False

        self.overlay = Adw.ToastOverlay()
        self.overlay.set_child(self.viewport_box)
        self.set_child(self.overlay)
        self.connect('show', self.on_show)
        self.set_active_category('smileys-emotion')

        # self.emoji_list.connect('move-cursor', lambda x, w, e, r, b: print('test'))

    def on_hide(self):
        self.search_entry.set_text('')
        self.query = None
        self.selection = []
        self.update_list_tip(None)
        for button in self.selected_buttons:
            button.get_style_context().remove_class('selected')

        self.selected_buttons = []

    def on_activation(self):
        self.present_with_time(time.time())
        self.grab_focus()

        self.set_focus(self.search_entry)

    def on_show(self, widget: Gtk.Window):
        pass

    # Create stuff
    def create_menu_button(self):
        builder = Gtk.Builder()
        builder.add_from_resource('/it/mijorus/smile/ui/menu.xml')
        menu = builder.get_object('primary_menu')

        return Gtk.MenuButton(popover=menu, icon_name='open-menu-symbolic')

    def create_emoji_button(self, data: dict):
        button = EmojiButton(data)
        button.connect('clicked', self.handle_emoji_button_click)

        return button

    def create_category_picker(self) -> Gtk.ScrolledWindow:
        scrolled = Gtk.ScrolledWindow(name='emoji_categories_box')
        box = Gtk.Box(spacing=4)

        i = 0
        for c, cat in emoji_categories.items():
            if 'icon' in cat:
                button = Gtk.Button(label=cat['icon'], valign=Gtk.Align.CENTER)
                button.category = c
                button.index = i
                button.connect('clicked', self.filter_for_category)

                box.append(button)
                self.category_picker_widgets.append(button)
                i += 1

        scrolled.set_child(box)
        self.categories_count = i
        return scrolled

    def create_emoji_list(self) -> Gtk.FlowBox:
        flowbox = Gtk.FlowBox(valign=Gtk.Align.START,
                              homogeneous=True,
                              name='emoji_list_box',
                              selection_mode=Gtk.SelectionMode.NONE,
                              max_children_per_line=self.emoji_grid_col_n,
                              min_children_per_line=self.emoji_grid_col_n
                              )

        flowbox.set_filter_func(self.filter_emoji_list, None)
        flowbox.set_sort_func(self.sort_emoji_list, None)

        start = time.time_ns()
        for i, e in emojis.items():
            emoji_button = self.create_emoji_button(e)
            flowbox_child = FlowBoxChild(emoji_button)

            is_recent = (e['hexcode'] in get_history())
            flowbox.append(flowbox_child)
            self.emoji_list_widgets.append(flowbox_child)

            if is_recent:
                self.history_size += 1

        print('Emoji list creation took ' + str((time.time_ns() - start) // 1000000) + 'ms')
        return flowbox

    # Handle events
    def handle_emoji_button_click(self, widget: Gtk.Button):
        if (self.shift_key_pressed):
            self.select_button_emoji(widget)
        else:
            self.copy_and_quit(widget)

    # Handle key-presses
    def handle_window_key_release(self, widget, event: Gdk.Event):
        if (event.keyval == Gdk.KEY_Shift_L or event.keyval == Gdk.KEY_Shift_R):
            self.shift_key_pressed = False

    # Handle every possible keypress here, returns True if the event was handled (prevent default)
    def handle_window_key_press(self, controller: Gtk.EventController, keyval: int, keycode: int, state: Gdk.ModifierType) -> bool:
        if (keyval == Gdk.KEY_Escape):
            self.default_hiding_action()
            return True

        self.shift_key_pressed = (keyval == Gdk.KEY_Shift_L or keyval == Gdk.KEY_Shift_R)

        ctrl_key = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift_key = bool(state & Gdk.ModifierType.SHIFT_MASK)
        alt_key = bool(state & Gdk.ModifierType.ALT_MASK)

        is_modifier = ctrl_key or shift_key or alt_key
        string = keycode

        focused_widget = self.get_focus()
        focused_button = None
        

        if isinstance(focused_widget, FlowBoxChild):
            focused_button = focused_widget.emoji_button

        if self.search_entry is focused_widget.get_parent():
            if (keyval == Gdk.KEY_Down):
                self.load_first_row()
                self.emoji_grid_first_row[0].grab_focus()
                # self.emoji_list.emit('move-cursor', Gtk.MovementStep.VISUAL_POSITIONS, 0, False, True)

                return True

            # return False

        if alt_key:
            if focused_button and keyval == Gdk.KEY_e:
                if not SkintoneSelector.check_skintone(focused_widget):
                    self.overlay.add_toast(
                        Adw.Toast(title="No skintones available", timeout=1)
                    )
                else:
                    SkintoneSelector(focused_widget, self, self.handle_emoji_button_click)
                    return True

            elif focused_button and keyval == Gdk.KEY_t:
                CustomTagEntry(focused_widget, self)
                return True

            elif keyval in [Gdk.KEY_Left, Gdk.KEY_Right]:
                next_sel = None
                if keyval == Gdk.KEY_Left:
                    next_sel = self.selected_category_index - 1 if (self.selected_category_index > 0) else 0
                elif keyval == Gdk.KEY_Right:
                    next_sel_index = (self.categories_count - 1)
                    next_sel = self.selected_category_index + 1 if (self.selected_category_index < (next_sel_index)) else (next_sel_index)
                    
                if next_sel != None:
                    for child in list(self.category_picker_widgets):
                        if child.index == next_sel:
                            self.filter_for_category(child)
                            return True

            return False

        if shift_key:
            if (keyval == Gdk.KEY_Return):
                if focused_button:
                    self.select_button_emoji(focused_button)
                    return True

            elif (keyval == Gdk.KEY_BackSpace):
                if focused_button:
                    if len(self.selection) > 0:
                        last_button = self.selected_buttons[-1]

                        self.selection.pop()
                        self.selected_buttons.pop()

                        if not self.selection.__contains__(last_button.get_label()):
                            last_button.get_style_context().remove_class('selected')
                        self.update_selection_content(self.selection)

                    return True

        if ctrl_key:
            if keyval == Gdk.KEY_question:
                shortcut_window = ShortcutsWindow()
                shortcut_window.open()

            if (keyval == Gdk.KEY_Return):
                if len(self.selection):
                    self.copy_and_quit()
                    return True

        else:
            # Focus is on an emoji button
            if focused_button:
                if (keyval == Gdk.KEY_Return):
                    self.copy_and_quit(focused_button)
                    return True
                elif (keyval == Gdk.KEY_Up):
                    if isinstance(focused_button.props.parent, Gtk.FlowBoxChild) and (focused_button in self.emoji_grid_first_row):
                        self.search_entry.grab_focus()
                        return False
                elif (not is_modifier) and (keycode == 1) and re.match(r'\S', string):
                    self.search_entry.grab_focus()

            # Focus is on a category button
            elif isinstance(focused_widget, Gtk.Button) and hasattr(focused_widget, 'category'):
                # Triggers when we press arrow up on the category picker
                az_re = re.compile(r"[a-z]", re.IGNORECASE)
                if (keyval in [Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Left, Gdk.KEY_Right]) and re.match(az_re, string):
                    self.search_entry.grab_focus()
                else:
                    if (keyval == Gdk.KEY_Up):
                        self.set_active_category(focused_widget.category)

                        for f in self.emoji_list_widgets:
                            if self.selected_category == 'recents':
                                if f.emoji_button.hexcode in get_history():
                                    f.emoji_button.grab_focus()
                                    break
                            else:
                                if f.emoji_button.emoji_data['group'] == self.selected_category:
                                    f.emoji_button.grab_focus()
                                    break

                        return True

        return False

    def default_hiding_action(self):
        if (self.settings.get_boolean('iconify-on-esc')):
            self.iconify()
        else:
            self.hide()

        self.on_hide()

    # # # # # #
    def update_list_tip(self, text: str = None):
        if (text is None):
            self.list_tip_revealer.set_reveal_child(False)
        else:
            self.list_tip_label.set_label(text)
            self.list_tip_revealer.set_reveal_child(True)

    def update_selection_content(self, title: str = None):
        self.update_list_tip('Selected: ' + ''.join(title[-8:]))

    def set_active_category(self, category: str):
        for b in []:
            if b.category != category:
                b.get_style_context().remove_class('selected')
            else:
                b.get_style_context().add_class('selected')

    def select_button_emoji(self, button: EmojiButton):
        if not button.emoji_is_selected:
            self.selection.append(button.get_label())
            increament_emoji_usage_counter(button)

            self.selected_buttons.append(button)
            button.emoji_is_selected = True

            button.toggle_select()
            self.update_selection_content(self.selection)

    def load_first_row(self):
        self.emoji_grid_first_row = []
        for widget in self.emoji_list_widgets:
            if (len(self.emoji_grid_first_row) < self.emoji_grid_col_n) and widget.props.visible:
                self.emoji_grid_first_row.append(widget)

    def filter_for_category(self, widget: Gtk.Button):
        self.set_active_category(None)
        widget.grab_focus()

        self.query = None
        self.selected_category = widget.category
        self.selected_category_index = widget.index
        self.category_picker.set_opacity(1)

        self.emoji_list.invalidate_filter()

        if widget.category == 'recents':
            self.update_list_tip('Recently used emojis' if (len(get_history())) else "Whoa, it's still empty! \nYour most used emojis will show up here\n")
        elif len(self.selected_buttons) == 0:
            self.update_list_tip(None)

        self.emoji_list.invalidate_sort()
        self.load_first_row()

    def copy_and_quit(self, button: Gtk.Button = None):
        text = ''
        if button:
            text = button.get_label()
            increament_emoji_usage_counter(button)

        contx = Gdk.ContentProvider.new_for_value(''.join([*self.selection, text]))
        self.clipboard.set_content(contx)

        if self.settings.get_boolean('is-first-run'):
            n = Gio.Notification.new('Copied!')
            n.set_body("I have copied the emoji to the clipboard. You can now paste it in any input field.")
            n.set_icon(Gio.ThemedIcon.new('dialog-information'))

            Gio.Application.get_default().send_notification('copy-message', n)
            self.settings.set_boolean('is-first-run', False)

        self.default_hiding_action()

    def search_emoji(self, search_entry: str):
        query = search_entry.get_text().strip()

        self.query = query if query else None
        list_was_sorted = self.query != None

        self.emoji_list.invalidate_filter()

        if (self.list_was_sorted != list_was_sorted):
            if query:
                for child in self.emoji_list_widgets:
                    if get_custom_tags(child.emoji_button.emoji_data['hexcode'], True):
                        child.changed()
            else:
                self.emoji_list.invalidate_sort()

        self.list_was_sorted = list_was_sorted

    def filter_emoji_list(self, widget: Gtk.FlowBoxChild, user_data):
        e = (widget.get_child()).emoji_data
        filter_result = True

        localized_tags = []
        if self.settings.get_boolean('use-localized-tags') and self.settings.get_string('tags-locale') != 'en':
            localized_tags = get_localized_tags(self.settings.get_string('tags-locale'), e['hexcode'], Gio.Application.get_default().datadir)

        merge_en_tags = self.settings.get_boolean('use-localized-tags') and self.settings.get_boolean('merge-english-tags')

        if self.query:
            if self.query == e['emoji']:
                filter_result = True
            elif get_custom_tags(e['hexcode'], cache=True) and tag_list_contains(get_custom_tags(e['hexcode'], cache=True), self.query):
                filter_result = True
            elif (not self.settings.get_boolean('use-localized-tags')):
                filter_result = tag_list_contains(e['tags'], self.query)
            elif self.settings.get_boolean('use-localized-tags'):
                if self.settings.get_boolean('merge-english-tags'):
                    filter_result = tag_list_contains(','.join(localized_tags), self.query) or tag_list_contains(e['tags'], self.query)
                else:
                    filter_result = tag_list_contains(','.join(localized_tags), self.query)

            else:
                filter_result = False

        elif self.selected_category:
            if self.selected_category == 'recents':
                filter_result = (widget.get_child()).hexcode in get_history()
            else:
                filter_result = self.selected_category == e['group']

        else:
            filter_result = e['group'] == self.selected_category

        if filter_result:
            widget.show()
        else:
            widget.hide()

        return filter_result

    def sort_emoji_list(self, child1: Gtk.FlowBoxChild, child2: Gtk.FlowBoxChild, user_data):
        child1 = child1.get_child()
        child2 = child2.get_child()

        if (self.selected_category == 'recents'):
            h1 = get_history()[child1.hexcode] if child1.hexcode in get_history() else None
            h2 = get_history()[child2.hexcode] if child2.hexcode in get_history() else None
            return ((h2['lastUsage'] if h2 else 0) - (h1['lastUsage'] if h1 else 0))

        elif self.query:
            return -1 if get_custom_tags(child1.hexcode, True) else 1

        else:
            return (child1.emoji_data['order'] - child2.emoji_data['order'])

    def update_emoji_skintones(self, settings: Gio.Settings, key):
        modifier_settings = self.settings.get_string('skintone-modifier')
        for child in self.emoji_list.get_children():
            emoji_button = child.get_children()[0]

            if 'skintones' in emoji_button.emoji_data:
                if len(modifier_settings):
                    for tone in emoji_button.emoji_data['skintones']:
                        if f'-{modifier_settings}' in tone['hexcode']:
                            emoji_button.set_label(tone['emoji'])
                            break
                else:
                    emoji_button.set_label(emoji_button.emoji_data['emoji'])
