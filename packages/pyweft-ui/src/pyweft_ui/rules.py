"""Checks for the fields of a :class:`~pyweft_ui.Form`.

Each function here returns a rule: a function the form calls with the
field's value, which returns a message when the value isn't right and None
when it is. Use them through the module, so they never clash with a field
of the same name::

    from pyweft_ui import Form, rules

    form = Form(email=[rules.required(), rules.email()])

Every rule but :func:`required` and :func:`accepted` lets an empty value
through: put ``required()`` first when the field must be filled in.

Your own rule is a function of the value, returning a message or None::

    def no_spaces(value):
        return "Leave out the spaces" if " " in value else None

or, for a test that is simply true or false, :func:`check`. A rule that
also takes a second argument gets the form, to read other fields:
``form.value("password")``.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable

Rule = Callable[..., "str | None"]

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s.]+$")
_URL = re.compile(r"^https?://[^\s/$.?#][^\s]*\.[^\s]*$", re.IGNORECASE)


def is_empty(value: Any) -> bool:
    """None, blank text, and empty lists, sets and dicts. Not 0 or False."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, frozenset, dict)):
        return not value
    return False


def required(message: str = "This is required") -> Rule:
    """The field must have a value (see :func:`is_empty`)."""
    def rule(value):
        return message if is_empty(value) else None
    return rule


def accepted(message: str = "Tick this to continue") -> Rule:
    """A checkbox or switch that must be on, such as agreeing to terms."""
    def rule(value):
        return None if value is True else message
    return rule


def email(message: str = "Enter an email address, like name@example.com") -> Rule:
    """Text shaped like an email address."""
    def rule(value):
        return None if is_empty(value) or _EMAIL.match(str(value).strip()) else message
    return rule


def url(message: str = "Enter a web address starting with https://") -> Rule:
    """An http or https address."""
    def rule(value):
        return None if is_empty(value) or _URL.match(str(value).strip()) else message
    return rule


def min_length(n: int, message: str | None = None) -> Rule:
    """At least ``n`` characters of text, or ``n`` items of a list."""
    def rule(value):
        if is_empty(value) or len(value) >= n:
            return None
        if message:
            return message
        return f"Use at least {n} characters" if isinstance(value, str) else f"Choose at least {n}"
    return rule


def max_length(n: int, message: str | None = None) -> Rule:
    """At most ``n`` characters of text, or ``n`` items of a list."""
    def rule(value):
        if is_empty(value) or len(value) <= n:
            return None
        if message:
            return message
        return f"Use at most {n} characters" if isinstance(value, str) else f"Choose at most {n}"
    return rule


def min_value(n: float, message: str | None = None) -> Rule:
    """A number of at least ``n``."""
    def rule(value):
        return None if is_empty(value) or value >= n else (message or f"Must be at least {n}")
    return rule


def max_value(n: float, message: str | None = None) -> Rule:
    """A number of at most ``n``."""
    def rule(value):
        return None if is_empty(value) or value <= n else (message or f"Must be at most {n}")
    return rule


def pattern(regex: str, message: str = "This doesn't look right") -> Rule:
    """Text that matches ``regex`` in full: ``pattern(r"[A-Z]{2}\\d{4}")``."""
    compiled = re.compile(regex)

    def rule(value):
        return None if is_empty(value) or compiled.fullmatch(str(value)) else message
    return rule


def one_of(choices: Iterable[Any], message: str | None = None) -> Rule:
    """One of ``choices``."""
    allowed = list(choices)

    def rule(value):
        if is_empty(value) or value in allowed:
            return None
        return message or "Choose one of: " + ", ".join(str(c) for c in allowed)
    return rule


def same_as(field: str, message: str = "These don't match") -> Rule:
    """The same value as another field of the form, as when a password is
    typed twice: ``confirm=rules.same_as("password")``."""
    def rule(value, form):
        return None if value == form.value(field) else message
    return rule


def check(test: Callable[[Any], Any], message: str) -> Rule:
    """Your own test: ``check(lambda v: v != "admin", "That name is taken")``.
    ``test`` gets the value and returns something true when it's fine."""
    def rule(value):
        return None if is_empty(value) or test(value) else message
    return rule
