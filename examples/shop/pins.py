"""Orders the user pinned, shared by every page and the header.

A Store: change it from any component (or a timer, or a task) and every
page showing it updates.
"""

from pyweft import Store


class Pins(Store):
    ids: list = []

    @property
    def count(self):
        return len(self.ids)

    def toggle(self, order_id):
        if order_id in self.ids:
            self.ids.remove(order_id)
        else:
            self.ids.append(order_id)


pins = Pins()
