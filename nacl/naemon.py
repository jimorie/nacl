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
    A `DataObject` for Naemon object definitions. See `ConfigStream` for
    examples.
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

    def __init__(self, objtype: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.objtype = objtype

    @classmethod
    def load(cls, lines: Lines, source_file: DataFile = None):
        """
        Read the next Naemon object definition from the `lines` stream.
        Non-object definition lines are ignored.
        """

        try:
            while True:
                linenum, line = next(lines)
                if line.startswith("define "):
                    line = line[len("define ") :]
                    break
            if source_file:
                source_file.handle_prefix()
            if "{" in line:
                line = line.strip(" {")
            else:
                # Assume next line holds the single {
                next(lines)
            objdef = cls(line, linenum=linenum, source_file=source_file)
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

    def dump(self, stream: t.TextIO):
        """
        Write the Naemon object definition of this object to `stream`.
        """
        stream.write(f"define {self.objtype} {{\n")
        for k, v in self.items():
            stream.write(f"    {k:{self.keywidth}} {v}\n")
        stream.write("}\n")

    def autoconvert(self, key, value):
        """
        Convert known Nameon object directives from their parsed string values
        to their proper Python values, as defined by our `conversion_table`.
        """
        if key in self.conversion_table:
            try:
                return self.conversion_table[key](value)
            except (ValueError, TypeError):
                pass
        return value

    @register_name
    def type(self):
        """
        Return the name of this Naemon object type when this object is
        queried for the item key "type".
        """
        return self.objtype


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
        >>> objlist = list(ConfigStream(stream).read_objects())
        >>> len(objlist)
        1

        >>> obj = objlist[0]
        >>> obj
        ObjectDefinition([('host_name', 'foo'), ('register', '1')])

        >>> obj["type"]
        'host'

        >>> obj["host_name"]
        'foo'

        >>> obj["register"]
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
    """

    @register_function
    def has_member(collection, *members):
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
    def in_collection(a, b):
        """
        Make the `in` operator more lenient with `None` values.
        """
        if not b:
            return False
        return a in b

    @register_operator(key=ast.NotIn)
    def not_in_collection(a, b):
        """
        The `not in` operator simply inverts the `in` operator, as defined
        above.
        """
        return not ObjdefFilter.in_collection(a, b)


class ObjdefUpdate(ObjdefFilter):
    """
    A custom `Expression` tweaked for updating `ObjectDefinition` data.
    """

    def _eval_assign(self, node):
        """
        Update a value in the object definition. This implements the `=`
        operator.
        """
        value = self._eval(node.value)
        for target in node.targets:
            self.dataobject.update(target.id, value)
        return value

    def _eval_aug_assign(self, node):
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
            self.dataobject.update(node.target.id, ",".join(left_value))
        else:
            return super()._eval_aug_assign(node)
