""" Extensions to the click library that convert input to `Expression` objects. """

import typing as t

import click

from nacl.expression import Expression
from nacl.errors import errorhandler


class FilterType(click.ParamType):
    """
    A `click.ParamType` that converts the parameter input to an `Expression`
    object instance. All `Expression` instances are also collected in the
    class variable `registered_filters`.
    """

    registered_filters: t.List[Expression] = []
    name = "FILTER"

    def __init__(self, filter_cls: Expression = None, register_filter=True):
        super().__init__()
        self.filter_cls = filter_cls or Expression
        self.register_filter = register_filter

    @errorhandler
    def convert(self, value: t.Any, *_) -> Expression:
        if isinstance(value, self.filter_cls):
            return value
        expr = self.parse_filter(value)
        if self.register_filter:
            self.registered_filters.append(expr)
        return expr

    def parse_filter(self, expr: str) -> Expression:
        return self.filter_cls(expr)

    @staticmethod
    def escape(value):
        return (
            value.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').strip()
        )


class MacroFilterType(FilterType):
    """
    A `FilterType` that expands the parameter input by putting it into a
    format defined by the class variable `macro`.
    """

    macro = "{}"

    def parse_filter(self, expr: str) -> Expression:
        return super().parse_filter(self.macro.format(expr))


class CommandType(MacroFilterType):
    """
    Filter commands on their command_name.
    """

    name = "COMMAND_NAME"
    macro = "type == 'command' and command_name == '{}'"


class ContactType(MacroFilterType):
    """
    Filter contacts on their contact_name.
    """

    name = "CONTACT_NAME"
    macro = "type == 'contact' and contact_name == '{}'"


class HostType(MacroFilterType):
    """
    Filter hosts on their host_name.
    """

    name = "HOST_NAME"
    macro = "type == 'host' and host_name == '{}'"


class HostgroupType(MacroFilterType):
    """
    Filter hostgroups on their hostgroup_name.
    """

    name = "HOSTGROUP_NAME"
    macro = "type == 'hostgroup' and hostgroup_name == '{}'"


class ServiceType(FilterType):
    """
    Filter services on their host_name and service_description, separated by
    semicolon.
    """

    name = "HOST_NAME;SERVICE_DESCRIPTION"

    def parse_filter(self, expr: str) -> Expression:
        if ";" in expr:
            host_name, service_description = expr.split(";", 1)
            expr = (
                "type == 'service' and host_name == '{}' "
                "and service_description == '{}'"
            ).format(
                self.escape(host_name),
                self.escape(service_description),
            )
        else:
            expr = "type == 'service' and service_description == '{}'".format(
                self.escape(expr),
            )
        return super().parse_filter(expr)


class ServicegroupType(MacroFilterType):
    """
    Filter servicegroups on their servicegroup_name.
    """

    name = "SERVICEGROUP_NAME"
    macro = "type == 'servicegroup' and servicegroup_name == '{}'"


class FilterFile(FilterType, click.Path):
    """
    A `FilterType` that reads filters from file.
    """

    name = "FILTER_FILE"

    def __init__(self, filter_cls: Expression, *args, **kwargs):
        FilterType.__init__(self, filter_cls)
        click.Path.__init__(self, *args, **kwargs)

    def convert(self, value: t.Any, *args) -> t.List[Expression]:
        if isinstance(value, list):
            return value
        filepath = click.Path.convert(self, value, *args)
        values = []
        with open(filepath, "r") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    values.append(FilterType.convert(self, line, *args))
        return values
