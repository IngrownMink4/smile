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

import sys
import gi
import time
import os
import csv
from .lib.emoji_list import emojis

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gio, Gdk

class Picker(Gtk.Window):
    def __init__(self):
        super().__init__(title="Smile")
        self.connect('key_press_event', self.quit_on_escape)
        self.set_border_width(5)
        self.set_default_size(200, 350)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.MOUSE)
        
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)

        # Create the emoji list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.box = Gtk.Box(orientation = Gtk.Orientation.VERTICAL)
        self.query = None

        self.emoji_list = self.create_emoji_list()
        scrolled.add(self.emoji_list)
        self.box.pack_start(scrolled, True, True, 0)
        self.box.pack_end(self.create_category_picker(), False, True, 3)
        
        # Create an header bar
        self.header_bar = Gtk.HeaderBar()
        self.header_bar.set_title('Smile')
        self.header_bar.props.subtitle = 'Type to search'
        self.header_bar.props.show_close_button = True
        

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_hexpand(True)
        self.search_entry.connect('search_changed', self.search_emoji)
        
        self.header_bar.pack_start(self.search_entry)
        self.set_titlebar(self.header_bar)

        self.add(self.box)
        self.connect('show', self.on_show)

    def on_show(self, widget: Gtk.Window):
        self.search_entry.set_text('')
        self.query = None
        self.set_focus(self.search_entry)
    
    def quit_on_escape(self, widget, event: Gdk.Event):
        if (event.keyval == Gdk.KEY_Escape):
            self.hide()

    def create_emoji_button(self, emoji: str):
        button = Gtk.Button()
        button.set_label(emoji)
        button.connect('clicked', self.copy_and_quit)

        return button

    def create_category_picker(self) -> Gtk.FlowBox:
        # box = Gtk.Box(orientation = Gtk.Orientation.HORIZONTAL)
        flowbox = Gtk.FlowBox()
        flowbox.set_valign(Gtk.Align.START)
        flowbox.set_max_children_per_line(7)
        flowbox.set_min_children_per_line(7)
        flowbox.set_homogeneous(True)
        flowbox.set_name('emoji_categories_box')
        
        for c, cat in self.get_emoji_category().items():
            if 'icon' in cat:
                button = Gtk.Button()
                button.set_label(cat['icon'])
                flowbox.add(button)

        return flowbox

    def copy_and_quit(self, button: Gtk.Button):
        clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clip.set_text(button.get_label(), -1)
        self.hide()

    def get_emoji_category(self) -> dict:
        return {
            'smileys-emotion': {
                'icon': '😀',
            }, 
            'animals-nature': {
                'icon': '🐶'
            }, 
            'food-drink': {
                'nested': 'animals-nature'
            }, 
            'travel-places': {
                'icon': '🚘️'
            }, 
            'component': {
                'nested': 'symbols'
            }, 
            'activities': {
                'icon': '⚽️'
            }, 
            'objects': {
                'icon': '💡'
            }, 
            'symbols': {
                'icon': '1️⃣'
            }, 
            'flags': {
                'icon': '🏳️'
            }, 
            'people-body': {
                'nested': 'smileys-emotion'
            }, 
            'extras-unicode':{
                'nested': 'symbols'
            }
        }

    def search_emoji(self, search_entry: str):
        query = search_entry.get_text()
        self.query = None if (len(query) == 0) else query
        self.emoji_list.invalidate_filter()

    def create_emoji_list(self):
        flowbox = Gtk.FlowBox()
        flowbox.set_valign(Gtk.Align.START)
        flowbox.set_max_children_per_line(7)
        flowbox.set_min_children_per_line(7)
        flowbox.set_homogeneous(True)
        flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        flowbox.set_filter_func(self.filter_emoji_list, None)

        for i, e in enumerate(emojis):
            button = self.create_emoji_button(e['emoji'])
            button.emoji_dict = e
            button.tag = f"{e['annotation']} {e['tags']}".replace(',', '')
            flowbox.add(button)
        
        return flowbox

    def filter_emoji_list(self, widget: Gtk.FlowBoxChild, user_data):
        e = (widget.get_child()).emoji_dict

        if e['skintone'] != '':
            return False
        
        if self.query and (widget.get_child()).tag.lower().__contains__(self.query.lower()):
            return True
        
        elif (self.query == None or len(self.query) <= 1) and e['group'] == 'smileys-emotion':
            return True

        return False


