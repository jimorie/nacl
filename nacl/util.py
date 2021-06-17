""" Utility functions. """

import typing as t


class register_decorator:
    """
    Decorator class that can build a dict of all decorated methods.

    Typical use involves subclassing `register_decorator` since the decorator
    works by collecting all methods on a class that are instances
    of *itself*.

    Examples:

        >>> class my_decorator(register_decorator):
        ...     pass

        >>> class Foo:
        ...     @my_decorator
        ...     def foo(self):
        ...         return "foo"
        ...     def bar(self):
        ...         return "bar"

        >>> my_decorator.get_registered(Foo)
        {'foo': <function Foo.foo at ...>}

        >>> class Bar(Foo):
        ...     @my_decorator(key=(1,2,3))
        ...     def bar(self):
        ...         return "bar"

        >>> my_decorator.get_registered(Bar)
        {'foo': <function Foo.foo at ...>, (1, 2, 3): <function Bar.bar at ...>}

        >>> my_decorator.set_registered(Bar)
        >>> Bar.my_decorator
        {'foo': <function Foo.foo at ...>, (1, 2, 3): <function Bar.bar at ...>}
    """

    def __init__(self, decorated: t.Callable = None, key: t.Any = None):
        self.decorated = decorated
        self.key = key

    def __call__(self, *args, **kwargs):
        """
        Call the decorated method, unless undefined. In the latter case this
        is the decorating call, and we create a new instance of ourselves with
        both the decorated method and the parameters that this instance was
        created with.
        """
        if self.decorated:
            return self.decorated(*args, **kwargs)
        return self.__class__(*args, key=self.key)

    @classmethod
    def get_registered(cls, parent_cls: t.Type) -> t.Mapping:
        """
        Find all methods defined on `parent_cls` and its parent classes
        decorated by this class, and return a dict with the method names as
        keys and the original decorated methods as values. If the decorator
        was created with a `key` keyword argument, that value will be used as
        key instead of the method name.
        """
        return {
            (value.key or key): value.decorated
            for owner_cls in reversed((parent_cls, *parent_cls.__bases__))
            for key, value in owner_cls.__dict__.items()
            if isinstance(value, cls)
        }

    @classmethod
    def set_registered(cls, parent_cls: t.Type, register_name: str = None):
        """
        Set the dict returned by `get_registered` as a class variable on
        `parent_cls` with a name of `register_name`, unless previously set.
        If `register_name` is omitted, the name of this class is used
        instead.
        """
        register_name = register_name or cls.__name__
        if not hasattr(parent_cls, register_name):
            setattr(parent_cls, register_name, cls.get_registered(parent_cls))
