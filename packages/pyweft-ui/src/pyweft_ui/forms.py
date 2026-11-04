"""Form: checking a component's fields, and showing what needs fixing.

In a component's code block, name each field and its rules::

    from pyweft_ui import Form, rules

    email: str = ""
    password: str = ""

    form = Form(
        email=[rules.required(), rules.email()],
        password=[rules.required(), rules.min_length(8)],
    )

    async def submit(self):
        if not self.form.check():     # shows every error, focuses the first
            return
        ...

and in its template give each field its message, and say when it's left::

    <ui.TextField ref="email" label="Email" @bind="email"
                  :error="form.error('email')" @blur="form.touch('email')" />

A field shows no message until the user leaves it (``touch``) or tries to
submit (``check``); from then on its message follows what they type, so it
goes away as soon as the value is right. ``form.valid`` says whether every
field passes, to enable a button.

``Form`` works like ``@property``: each component gets its own state, and
it isn't a prop a parent can set.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

_STATE = "_form_state_"


def _as_rule(rule: Callable) -> Callable[[Any, Any], str | None]:
    """Every rule called as rule(value, form), whichever it takes."""
    if not callable(rule):
        raise TypeError(f"a Form rule is a function, got {rule!r}")
    try:
        params = [
            p for p in inspect.signature(rule).parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        takes_form = len(params) >= 2
    except (TypeError, ValueError):  # builtins without a signature
        takes_form = False
    return rule if takes_form else (lambda value, form: rule(value))


class Form(property):
    """The rules for a component's fields: ``Form(name=rule or [rules])``,
    where each name is a field of the component."""

    def __init__(self, **fields: Callable | list[Callable]):
        if not fields:
            raise TypeError("Form(...) needs a field: Form(email=rules.required())")
        self.rules = {
            name: [_as_rule(r) for r in (spec if isinstance(spec, (list, tuple)) else [spec])]
            for name, spec in fields.items()
        }
        self.name = "form"
        super().__init__(self._bound)

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    def _bound(self, owner: Any) -> BoundForm:
        return BoundForm(self, owner)


class BoundForm:
    """A component's form: what ``self.form`` (or ``form`` in a template)
    gives you."""

    def __init__(self, spec: Form, owner: Any):
        self._spec = spec
        self._owner = owner
        # Kept on the component, so it lives as long as the component does
        # and survives hot reload; the rules come from the class each time.
        self._state = owner.__dict__.setdefault(
            _STATE + spec.name, {"submitted": False, "touched": set()}
        )

    @property
    def fields(self) -> list[str]:
        """The field names, in the order they were given."""
        return list(self._spec.rules)

    def value(self, name: str) -> Any:
        """The current value of a field."""
        return getattr(self._owner, name)

    def problem(self, name: str) -> str:
        """The field's first failing rule's message, shown or not; "" if it
        passes."""
        if name not in self._spec.rules:
            raise KeyError(f"the form has no field {name!r}; its fields are {self.fields}")
        value = self.value(name)
        for rule in self._spec.rules[name]:
            message = rule(value, self)
            if message:
                return str(message)
        return ""

    def shown(self, name: str) -> bool:
        """Whether the field's message is showing: after it was left, or a
        submit was tried."""
        return self._state["submitted"] or name in self._state["touched"]

    def error(self, name: str) -> str:
        """The message to show under the field: "" until it's been left or
        a submit was tried, and while it passes."""
        return self.problem(name) if self.shown(name) else ""

    @property
    def errors(self) -> dict[str, str]:
        """``{field: message}`` for every field showing a message."""
        return {name: msg for name in self.fields if (msg := self.error(name))}

    @property
    def valid(self) -> bool:
        """True when every field passes, whether or not messages show."""
        return not any(self.problem(name) for name in self.fields)

    @property
    def first_problem(self) -> str | None:
        """The first field, in order, that doesn't pass; None if all do."""
        return next((name for name in self.fields if self.problem(name)), None)

    def touch(self, name: str) -> None:
        """The user left the field: show its message from now on. Wire it
        to the field with ``@blur="form.touch('email')"``."""
        if name not in self._spec.rules:
            raise KeyError(f"the form has no field {name!r}; its fields are {self.fields}")
        self._state["touched"].add(name)

    def check(self, focus: bool = True) -> bool:
        """For submitting: show every message, and return True when all
        fields pass. Unless ``focus=False``, the cursor goes to the first
        field to fix, if it has a ``ref`` of the same name."""
        self._state["submitted"] = True
        first = self.first_problem
        if first is not None and focus and hasattr(self._owner, "focus"):
            self._owner.focus(first)
        return first is None

    def reset(self) -> None:
        """Hide every message again, as before the first submit: after
        saving, when the fields start over empty."""
        self._state["submitted"] = False
        self._state["touched"].clear()
