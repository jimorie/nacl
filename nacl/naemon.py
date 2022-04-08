""" Naemon specific implementations of parsers and data objects. """

import ast
import typing as t

from nacl.expression import Expression, register_function, register_operator
from nacl.parsers import (
    DataObject,
    DataStream,
    DataFile,
    register_name,
)
from nacl.typing import Lines


class ObjectDefinition(DataObject):
    """
    Base `DataObject` class for Naemon object definitions.

    Direct instances of `ObjectDefinition` must be created with an `objtype`
    as the first parameter. Sub-classes can bypass this by defining the
    `objtype` property or use the `register_type` decorator.

    Examples:

        >>> ObjectDefinition("foo")
        ObjectDefinition()

        >>> ObjectDefinition("foo")["type"]
        'foo'

        >>> ObjectDefinition()
        Traceback (most recent call last):
          ...
        TypeError: __init__() missing 1 required positional argument: 'objtype'

        >>> class Foo(ObjectDefinition):
        ...     objtype = "foo"

        >>> Foo()
        Foo()

        >>> Foo()["type"]
        'foo'
    """

    keywidth = 30
    conversion_table = {
        "active_checks_enabled": int,
        "check_freshness": int,
        "check_interval": int,
        "event_handler_enabled": int,
        "first_notification_delay": int,
        "flap_detection_enabled": int,
        "freshness_threshold": int,
        "high_flap_threshold": int,
        "hourly_value": int,
        "is_volatile": int,
        "low_flap_threshold  ": int,
        "max_check_attempts": int,
        "notification_interval": int,
        "notifications_enabled": int,
        "obsess": int,
        "obsess_over_host": int,
        "obsess_over_service": int,
        "passive_checks_enabled": int,
        "process_perf_data": int,
        "register": int,
        "retain_nonstatus_information": int,
        "retain_status_information": int,
        "retry_interval": int,
    }
    registered_types: t.Mapping[str, DataObject] = {}
    objtype = None

    def __init__(self, *args, **kwargs):
        if self.objtype is None:
            try:
                self.objtype, *args = args
            except ValueError:
                raise TypeError(
                    "__init__() missing 1 required positional argument: 'objtype'"
                )
        super().__init__(*args, **kwargs)

    def __eq__(self, other: "ObjectDefinition") -> bool:
        """
        Return true if `self` and `other` have equal `objtype` properties, as
        well as being equal as dicts.

        Examples:

            >>> ObjectDefinition("foo") == ObjectDefinition("foo")
            True

            >>> ObjectDefinition("foo", {"foo": 1}) == \\
            ... ObjectDefinition("foo", {"foo": 1})
            True

            >>> ObjectDefinition("foo", {"foo": 1}) == \\
            ... ObjectDefinition("foo", foo=1)
            True

            >>> ObjectDefinition("foo", {"foo": 1}) == \\
            ... ObjectDefinition("foo", {"foo": 2})
            False

            >>> ObjectDefinition("foo") == ObjectDefinition("bar")
            False

            >>> ObjectDefinition("foo") == dict()
            False
        """
        try:
            return self.objtype == other.objtype and super().__eq__(other)
        except AttributeError:
            return False

    @classmethod
    def load(cls, lines: Lines, source_file: DataFile = None) -> "ObjectDefinition":
        """
        Read the next Naemon object definition from the `lines` stream.
        Non-object definition lines are ignored.

        See `ConfigStream` for examples.
        """

        try:
            # Ignore lines we read until we hit one that starts with "define".
            while True:
                linenum, line = next(lines)
                if line.startswith("define "):
                    line = line[len("define ") :]
                    break
            # Call handle_prefix to flush all ignored lines. (Only matters if
            # we are in copymode.)
            if source_file:
                source_file.handle_prefix()
            # Strip away non-essential characters from the definition
            if "{" in line:
                line = line.strip(" {")
            else:
                # Assume next line holds the single {
                next(lines)
            # At this point `line` should be just the object type name and we
            # can create an object representation for it.
            objdef = cls.from_type(line, linenum=linenum, source_file=source_file)
            # Next we read all object directives until we hit a closing "}".
            for linenum, line in lines:
                if line == "}":
                    break
                k, v = line.split(" ", 1)
                objdef[k] = v.strip()
            return objdef
        except ValueError as exc:
            if source_file:
                location = f"{source_file.name} line {linenum}"
            else:
                location = f"line {linenum}"
            raise RuntimeError(f"Unsupported syntax at {location}: {exc}")

    def dump(self, stream: t.TextIO, selected: t.Optional[t.Mapping] = None):
        """
        Write the Naemon object definition of this object to `stream`. If `selected`
        is specified, write only object directives included therein.

        Examples:

            >>> print(
            ...     ObjectDefinition("host", {
            ...         "host_name": "foo", "contacts": "gurka,tomat"
            ...     }).dumps()
            ... )
            define host {
                host_name                      foo
                contacts                       gurka,tomat
            }
            <BLANKLINE>

            >>> print(
            ...     ObjectDefinition("host", {
            ...         "host_name": "foo", "contacts": "gurka,tomat"
            ...     }).dumps(selected=("contacts",))
            ... )
            define host {
                contacts                       gurka,tomat
            }
            <BLANKLINE>
        """
        stream.write(f"define {self.objtype} {{\n")
        for k, v in self.items():
            if selected is None or k in selected:
                if v is not None and v != "":
                    stream.write(f"    {k:{self.keywidth}} {v}\n")
        stream.write("}\n")

    def autoconvert(self, key: str, value: str) -> t.Any:
        """
        Convert known Nameon object directives from their parsed string values
        to their proper Python values, as defined by our `conversion_table`.

        Examples:

            >>> host = ObjectDefinition("host", {
            ...     "host_name": "foo", "check_interval": "3", "_FOO": "3"
            ... })
            >>> host["check_interval"]
            3

            >>> host["_FOO"]
            '3'

            >>> host["_BAR"] is None
            True
        """
        if key in self.conversion_table:
            try:
                return self.conversion_table[key](value)
            except (ValueError, TypeError):
                pass
        return value

    @register_name
    def type(self) -> str:
        """
        Return the name of this Naemon object type when this object is
        queried for the item key "type".

        Examples:

            >>> ObjectDefinition("host")["type"]
            "host"

            >>> ObjectDefinition("service")["type"]
            "service"
        """
        return self.objtype

    @property
    def identifier(self) -> t.Optional[str]:
        """
        Return a unique identifier for this object type, if any.

        Examples:

            >>> ObjectDefinition("foo").identifier is None
            True
        """
        return None

    @classmethod
    def register_type(cls, objtype: str) -> type:
        """
        Class decorator for registering a class definition that should be used
        for the given object type by `from_type`.

        Examples:

            >>> @ObjectDefinition.register_type("foo")
            ... class Foo(ObjectDefinition):
            ...     pass

            >>> Foo()["type"]
            'foo'

            >>> import io
            >>> stream = io.StringIO(
            ...     "define foo {\\n"
            ...     "    name   foo\\n"
            ...     "}\\n"
            ...     "define bar {\\n"
            ...     "    name   bar\\n"
            ...     "}"
            ... )
            >>> list(ConfigStream(stream).read_objects())
            [Foo([('name', 'foo')]), ObjectDefinition([('name', 'bar')])]
        """

        def decorator(decorated):
            cls.registered_types[objtype] = decorated
            decorated.objtype = objtype
            return decorated

        return decorator

    @classmethod
    def from_type(cls, objtype: str, *args, **kwargs) -> "ObjectDefinition":
        """
        Create an instance for the given `objtype`. If `objtype` has been
        registered with `register_type`, then the registered class will be
        used. Otherwise the called class is used as fallback and initialized
        with `objtype` as the first parameter.

        Examples:

            >>> @ObjectDefinition.register_type("foo")
            ... class Foo(ObjectDefinition):
            ...     pass

            >>> ObjectDefinition.from_type("foo", name="Foo")
            Foo([('name', 'Foo')])

            >>> ObjectDefinition.from_type("bar", name="Bar")
            ObjectDefinition([('name', 'Bar')])

        """
        objcls = cls.registered_types.get(objtype, cls)
        if objcls.objtype:
            return objcls(*args, **kwargs)
        return objcls(objtype, *args, **kwargs)


class ConfigStream(DataStream):
    """
    A `DataStream` sub-class that parses `ObjectDefinition` instances.

    Examples:

        >>> import io
        >>> stream = io.StringIO(
        ...     "define host {\\n"
        ...     "    host_name   foo # This is a comment\\n"
        ...     "    register    1\\n"
        ...     "}"
        ... )
        >>> host, *_ = list(ConfigStream(stream).read_objects())
        >>> host
        Host([('host_name', 'foo'), ('register', '1')])

        >>> host["type"]
        'host'

        >>> host["host_name"]
        'foo'

        >>> host["register"]
        1
    """

    object_cls = ObjectDefinition


class ConfigFile(DataFile):
    """
    A `DataFile` sub-class that parses `ObjectDefinition` instances. See
    `ConfigStream` for examples.
    """

    object_cls = ObjectDefinition


class ObjdefFilter(Expression):
    """
    A custom `Expression` tweaked for evaluating `ObjectDefinition` data.

    Examples:

        >>> host = Host({"contacts": "foo,bar"})

        >>> ObjdefFilter("has_member(contacts, 'foo')").eval(host)
        True

        >>> ObjdefFilter("has_member(contacts, 'bar')").eval(host)
        True

        >>> ObjdefFilter("has_member(contacts, 'fo')").eval(host)
        False

        >>> ObjdefFilter("1 in None").eval(host)
        False

        >>> ObjdefFilter("1 not in None").eval(host)
        True
    """

    @register_function
    def has_member(collection: t.Any, *members: t.List[t.Any]) -> bool:
        """
        Test if `collection` contains all of `members`, where `collection` is
        a comma-separated string of members.
        """
        if not collection:
            return False
        if isinstance(collection, str):
            collection = {member.strip() for member in collection.split(",")}
        return all(member in collection for member in members)

    @register_operator(key=ast.In)
    def in_collection(a: t.Any, b: t.Any) -> bool:
        """
        Make the `in` operator more lenient with `None` values.
        """
        if not b:
            return False
        return a in b

    @register_operator(key=ast.NotIn)
    def not_in_collection(a: t.Any, b: t.Any) -> bool:
        """
        The `not in` operator simply inverts the `in` operator, as defined
        above.
        """
        return not ObjdefFilter.in_collection(a, b)


class ObjdefUpdate(ObjdefFilter):
    """
    A custom `Expression` tweaked for updating `ObjectDefinition` data.

    Examples:

        >>> host = Host()
        >>> ObjdefUpdate("host_name = 'foo'").eval(host)
        'foo'

        >>> host
        Host([('host_name', 'foo')])

        >>> ObjdefUpdate("contacts += 'foo'").eval(host)
        'foo'

        >>> host
        Host([('host_name', 'foo'), ('contacts', 'foo')])

        >>> ObjdefUpdate("contacts += 'bar'").eval(host)
        'foo,bar'

        >>> host
        Host([('host_name', 'foo'), ('contacts', 'foo,bar')])

        >>> ObjdefUpdate("contacts -= 'foo'").eval(host)
        'bar'

        >>> host
        Host([('host_name', 'foo'), ('contacts', 'bar')])

        >>> ObjdefUpdate("contacts -= 'bar'").eval(host)
        >>> host
        Host([('host_name', 'foo')])
    """

    def _eval_assign(self, node: ast.AST) -> t.Any:
        """
        Update a value in the object definition. This implements the `=`
        operator.
        """
        value = self._eval(node.value)
        if value is not None and type(value) not in (str, int, float):
            raise RuntimeError(
                f"Config values can be of type string, int or float, but not: "
                f"{type(value).__name__}"
            )
        for target in node.targets:
            self.dataobject.update(target.id, value)
        return value

    def _eval_aug_assign(self, node: ast.AST) -> t.Any:
        """
        Update a value in the object definition by treating the left value as
        a comma-separated collection. This implements the `+=` and `-=`
        operators that adds and removes elements from the collection.
        """
        if any(isinstance(node.op, t) for t in (ast.Add, ast.Sub)):
            left_value = self.dataobject.get(node.target.id)
            left_value = left_value.split(",") if left_value else []
            right_value = self._eval(node.value)
            if isinstance(node.op, ast.Add):
                if right_value not in left_value:
                    left_value.append(right_value)
            elif right_value in left_value:
                left_value.remove(right_value)
            value = ",".join(left_value)
            self.dataobject.update(node.target.id, value)
            return value or None
        else:
            return super()._eval_aug_assign(node)


@ObjectDefinition.register_type("host")
class Host(ObjectDefinition):
    """
    An `ObjectDefinition` class for host objects.

    Examples:

        >>> Host() == ObjectDefinition.from_type("host")
        True

        >>> Host({"host_name": "foo"}).identifier
        'foo'

        >>> Host().identifier is None
        True
    """

    @property
    def identifier(self) -> t.Optional[str]:
        """Return `host_name` as the identifier."""
        return self["host_name"]


@ObjectDefinition.register_type("hostgroup")
class Hostgroup(ObjectDefinition):
    """
    An `ObjectDefinition` class for hostgroup objects.

    Examples:

        >>> Hostgroup() == ObjectDefinition.from_type("hostgroup")
        True

        >>> Hostgroup({"hostgroup_name": "foo"}).identifier
        'foo'

        >>> Hostgroup().identifier is None
        True
    """

    @property
    def identifier(self) -> t.Optional[str]:
        """Return `hostgroup_name` as the identifier."""
        return self["hostgroup_name"]


@ObjectDefinition.register_type("service")
class Service(ObjectDefinition):
    """
    An `ObjectDefinition` class for service objects.

    Examples:

        >>> Service() == ObjectDefinition.from_type("service")
        True

        >>> Service(
        ...     {"host_name": "foo", "service_description": "bar"}
        ... ).identifier
        'foo;bar'

        >>> Service().identifier is None
        True
    """

    @property
    def identifier(self) -> t.Optional[str]:
        """
        Return `host_name;service_description` as the identifier, or
        `hostgroup_name;service_description` for hostgroup services.
        """
        if self["host_name"]:
            return f"{self['host_name']};{self['service_description']}"
        if self["hostgroup_name"]:
            return f"{self['hostgroup_name']};{self['service_description']}"
        return self["service_description"]


@ObjectDefinition.register_type("servicegroup")
class Servicegroup(ObjectDefinition):
    """
    An `ObjectDefinition` class for servicegroup objects.

    Examples:

        >>> Servicegroup() == ObjectDefinition.from_type("servicegroup")
        True

        >>> Servicegroup({"servicegroup_name": "foo"}).identifier
        'foo'

        >>> Servicegroup().identifier is None
        True
    """

    @property
    def identifier(self) -> t.Optional[str]:
        """Return `servicegroup_name` as the identifier."""
        return self["servicegroup_name"]


@ObjectDefinition.register_type("contact")
class Contact(ObjectDefinition):
    """
    An `ObjectDefinition` class for contact objects.

    Examples:

        >>> Contact() == ObjectDefinition.from_type("contact")
        True

        >>> Contact({"contact_name": "foo"}).identifier
        'foo'

        >>> Contact().identifier is None
        True
    """

    @property
    def identifier(self) -> t.Optional[str]:
        """Return `contact_name` as the identifier."""
        return self["contact_name"]


@ObjectDefinition.register_type("contactgroup")
class Contactgroup(ObjectDefinition):
    """
    An `ObjectDefinition` class for contacgroup objects.

    Examples:

        >>> Contactgroup() == ObjectDefinition.from_type("contactgroup")
        True

        >>> Contactgroup({"contactgroup_name": "foo"}).identifier
        'foo'

        >>> Contactgroup().identifier is None
        True
    """

    @property
    def identifier(self) -> t.Optional[str]:
        """Return `contactgroup_name` as the identifier."""
        return self["contactgroup_name"]


@ObjectDefinition.register_type("command")
class Command(ObjectDefinition):
    """
    An `ObjectDefinition` class for command objects.

    Examples:

        >>> Command() == ObjectDefinition.from_type("command")
        True

        >>> Command({"command_name": "foo"}).identifier
        'foo'

        >>> Command().identifier is None
        True
    """

    @property
    def identifier(self) -> t.Optional[str]:
        """Return `command_name` as the identifier."""
        return self["command_name"]


@ObjectDefinition.register_type("timeperiod")
class Timeperiod(ObjectDefinition):
    """
    An `ObjectDefinition` class for timeperiod objects.

    Examples:

        >>> Timeperiod() == ObjectDefinition.from_type("timeperiod")
        True

        >>> Timeperiod({"timeperiod_name": "foo"}).identifier
        'foo'

        >>> Timeperiod().identifier is None
        True
    """

    @property
    def identifier(self) -> t.Optional[str]:
        """Return `timeperiod_name` as the identifier."""
        return self["timeperiod_name"]


@ObjectDefinition.register_type("hostdependency")
class Hostdependency(ObjectDefinition):
    """
    An `ObjectDefinition` class for hostdependency objects.

    Examples:

        >>> Hostdependency() == ObjectDefinition.from_type("hostdependency")
        True
    """

    pass


@ObjectDefinition.register_type("servicedependency")
class Servicedependency(ObjectDefinition):
    """
    An `ObjectDefinition` class for servicedependency objects.

    Examples:

        >>> Servicedependency() == ObjectDefinition.from_type("servicedependency")
        True
    """

    pass


@ObjectDefinition.register_type("hostescalation")
class Hostescalation(ObjectDefinition):
    """
    An `ObjectDefinition` class for hostescalation objects.

    Examples:

        >>> Hostescalation() == ObjectDefinition.from_type("hostescalation")
        True
    """

    pass


@ObjectDefinition.register_type("serviceescalation")
class Serviceescalation(ObjectDefinition):
    """
    An `ObjectDefinition` class for serviceescalation objects.

    Examples:

        >>> Serviceescalation() == ObjectDefinition.from_type("serviceescalation")
        True
    """

    pass
