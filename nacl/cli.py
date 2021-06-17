""" Command line interface for the nacl program. """

import collections
import contextlib
import itertools
import pathlib
import shutil
import sys
import typing as t

import click

from nacl.errors import errorhandler
from nacl.filters import (
    FilterType,
    HostType,
    ServiceType,
    CommandType,
    ContactType,
    HostgroupType,
    ServicegroupType,
    FilterFile,
)
from nacl.naemon import (
    ConfigFile,
    ConfigStream,
    ObjdefFilter,
    ObjdefUpdate,
)


class GlobPath(click.Path):
    """
    Extends `click.Path` to search directories for all directly contained
    files of a given glob pattern. The value returned by this type is
    therefore changed to a list of the given `path_type`.
    """

    def __init__(self, *args, glob: str = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.glob = glob

    def convert(self, value: t.Any, *args) -> t.List[t.Any]:
        if isinstance(value, list):
            return value
        path = pathlib.Path(value)
        if self.glob and path.is_dir():
            return [
                click.Path.convert(self, str(child), *args)
                for child in path.glob(self.glob)
            ]
        return [click.Path.convert(self, value, *args)]


@click.command()
@click.option(
    "--encoding",
    type=str,
    default="utf-8",
    show_default=True,
    help="""
        The encoding used in the configuration files.
    """,
)
@click.option(
    "--filter",
    "-f",
    multiple=True,
    type=FilterType(ObjdefFilter),
    help="""
        Return all object definitions that matches the given filter. Filters
        are written in a sandboxed Python-like language, with all object
        directives available as Python variables. Any filter expression that
        results in a truthy Python value will include the object definition
        in the result. Multiple filters can be given to expand the set of
        matching object definitions.
    """,
)
@click.option(
    "--filter-file",
    multiple=True,
    type=FilterFile(
        ObjdefFilter,
        exists=True,
        dir_okay=False,
    ),
    help="""
        Read filters from the given file. Each line in the file is treated as
        input to the `--filter` option.
    """,
)
@click.option(
    "--host",
    "-h",
    multiple=True,
    type=HostType(ObjdefFilter),
    help=HostType.__doc__,
)
@click.option(
    "--service",
    "-s",
    multiple=True,
    type=ServiceType(ObjdefFilter),
    help=ServiceType.__doc__,
)
@click.option(
    "--command",
    multiple=True,
    type=CommandType(ObjdefFilter),
    help=CommandType.__doc__,
)
@click.option(
    "--contact",
    multiple=True,
    type=ContactType(ObjdefFilter),
    help=ContactType.__doc__,
)
@click.option(
    "--hostgroup",
    multiple=True,
    type=HostgroupType(ObjdefFilter),
    help=HostgroupType.__doc__,
)
@click.option(
    "--servicegroup",
    multiple=True,
    type=ServicegroupType(ObjdefFilter),
    help=ServicegroupType.__doc__,
)
@click.option(
    "--update",
    "-u",
    multiple=True,
    type=FilterType(ObjdefUpdate, register_filter=False),
    help="""
        Update matching object definitions with the given expression. The
        expression syntax is the same as for --filter, with the addition that
        you can use the `=` operator to set a new value to a named object
        directive. Furthermore, the `+=` and `-=` operators can be used to
        add members and remove members from comma-separated collection
        values, e.g. for "contacts", "members", "hostgroups", and similar.
        Assigning a value of `None` or the empty string `""` removes the
        object directive entirely.
    """,
)
@click.option(
    "--overwrite",
    "-w",
    type=click.Choice(["no", "yes", "backup"]),
    default="no",
    show_default=True,
    help="""
        Control how updated configuration files are written. `no` writes
        updated configuration files to a new file with an added ".new"
        suffix. `yes` replaces the original configuration file with the
        updated file. `backup` adds a ".old" suffix to the original
        configuration file before replacing it with the updated file.
    """,
)
@click.option(
    "--count",
    "-c",
    multiple=True,
    type=str,
    help="""
        Count the number of object definitions that each distinct value of the
        given object directive appears in. With this option only the
        resulting counts are printed.
    """,
)
@click.option(
    "--metadata",
    "-m",
    type=click.Choice(["file", "filter", "total", "none"]),
    default=["file", "total"],
    show_default=True,
    multiple=True,
    help="""
        Print meta data information before the matching object definitions.
        `file` prints a reference to the line number and/or file name of the
        object definition. `filter` prints all filters that matched the
        object definition. `total` prints the total number of matched object
        definitions before exiting. `none` prints no meta data.
    """,
)
@click.option(
    "--oneline",
    is_flag=True,
    default=False,
    help="""Print only single line references to matching object definitions.""",
)
@click.argument(
    "config_files",
    type=GlobPath(exists=True, glob="*.cfg"),
    nargs=-1,
)
@errorhandler
def main(
    config_files: t.List[t.List[str]],
    **opt: t.Mapping,
):
    """
    The salty command line interface to your Naemon configuration.
    """
    with contextlib.ExitStack() as exitmanager:
        update_mode = bool(opt["update"])

        if config_files:
            # Open the file streams and register them with the exitmanager, so
            # that they are properly closed (and in case of update buffers,
            # deleted) on exit.
            config_files = [
                exitmanager.enter_context(
                    ConfigFile(name, encoding=opt["encoding"], update_mode=update_mode)
                )
                for name in itertools.chain.from_iterable(config_files)
            ]
            # Define an iterator over all the object definitions in the files.
            objdefs = itertools.chain.from_iterable(
                config_file.read_objects() for config_file in config_files
            )
        else:
            # Read object definitions from stdin when no config files are
            # given.
            objdefs = ConfigStream(sys.stdin).read_objects()
            if update_mode:
                # We don't know where to write updates when reading from
                # stdin.
                raise click.ClickException(
                    "Unable to use --update without named config files."
                )

        # Counter object for some basic analytics.
        counter = collections.Counter()
        # Counter object for the --count option
        if opt["count"]:
            groupcounter = collections.defaultdict(collections.Counter)
        # Get the list of all filter expressions registered via the various
        # options.
        registered_filters = FilterType.registered_filters

        # Iterate over all object definitions that we can parse from files or
        # stdin.
        for objdef in objdefs:
            if registered_filters:
                # Evaluate all filters against this object definition to see
                # if it matches.
                matches = [f for f in registered_filters if f.eval(objdef)]
            else:
                matches = None
            if not registered_filters or matches:
                if update_mode:
                    # Evaluate all update expressions against the matched
                    # object.
                    for update in opt["update"]:
                        update.eval(objdef)
                    # Calling handle_update will replace the old object
                    # definition in the updated config file with the updated
                    # one.
                    objdef.source_file.handle_update(objdef)

                if opt["count"]:
                    # Increment counters of queried object directives.
                    for directive in opt["count"]:
                        groupcounter[directive][objdef[directive]] += 1
                elif opt["oneline"]:
                    # Print a one-line representation of the object
                    # definition.
                    identifier = objdef.identifier
                    if identifier:
                        click.echo(
                            f"{objdef.objtype} '{identifier}' at {objdef.location}"
                        )
                    else:
                        click.echo(f"{objdef.objtype} at {objdef.location}")
                else:
                    # Print metadata options.
                    if "filter" in opt["metadata"]:
                        for match in matches:
                            click.echo(f"# Filter: {match.expr}")
                    if "file" in opt["metadata"]:
                        click.echo(f"# File: {objdef.location}")
                    # Print the matched object definition.
                    click.echo(objdef.dumps())

                counter["matched"] += 1
            elif update_mode:
                # Calling handle_unchanged will copy the old object definition
                # untouched to the updated config file.
                objdef.source_file.handle_unchanged()
            counter["total"] += 1

        # Print output for --count option.
        if opt["count"]:
            for directive, dircounts in groupcounter.items():
                header = f"Count: {directive}"
                click.echo(header)
                click.echo("=" * len(header))
                for v, n in dircounts.most_common():
                    click.echo(f"{n:<8} {'-' if v is None else v}")
                click.echo()

        # Print some final metadata.
        if "total" in opt["metadata"]:
            click.echo(
                f"# Total: {counter['matched']} / {counter['total']} "
                f"matching object definition(s)"
            )

        if update_mode:
            # Move updated files based on the --overwrite option.
            for config_file in config_files:
                if config_file.updated:
                    config_file.close()
                    if opt["overwrite"] == "no":
                        shutil.move(config_file.updated_name, config_file.name + ".new")
                    elif opt["overwrite"] == "yes":
                        shutil.move(config_file.updated_name, config_file.name)
                    elif opt["overwrite"] == "backup":
                        shutil.move(config_file.name, config_file.name + ".old")
                        shutil.move(config_file.updated_name, config_file.name)
