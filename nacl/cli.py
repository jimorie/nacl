""" Command line interface for the nacl program. """

import collections
import contextlib
import itertools
import os.path
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


TRANSACTION_SUFFIX = ".naclnew"
BACKUP_SUFFIX = ".naclold"


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
    "--delete",
    "-d",
    is_flag=True,
    help="""
        Delete matching object definitions.
    """,
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
    "--write",
    "-w",
    type=click.Choice(["overwrite", "backup", "transaction"]),
    default="transaction",
    show_default=True,
    help=f"""
        Control how updated configuration files are written. `overwrite`
        replaces the original configuration file with the updated file.
        `backup` adds a "{BACKUP_SUFFIX}" suffix to the original configuration
        file before replacing it with the updated file. `transaction` writes
        the updated file with a "{TRANSACTION_SUFFIX}" suffix. If the
        transaction file is already present, data will also be read from that
        file instead of the original. This allows multiple executions of the
        command to update the configuration files in steps, with previous
        updates being respected. See also the `--commit` option.
    """,
)
@click.option(
    "--no-transaction-check",
    is_flag=True,
    help="""
        When using `--write=transaction` or the `--commit` option, the command
        automatically fails if the modification time of the original file is
        newer than that of the transaction file. This option disabled that
        behavior.
    """,
)
@click.option(
    "--commit",
    is_flag=True,
    help="""
        Replace the original file(s) with their transaction file(s), if any.
        No other operatios are made.
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
    "--output",
    "-o",
    type=click.Choice(["naemon", "oneline", "value", "none"]),
    default="naemon",
    show_default=True,
    help="""
        Control how matching object definitions are printed. `naemon` prints
        the full object definition using Naemon configuration syntax. `oneline`
        prints a one-line reference of the object. `value` prints only the
        values of object directives when also using the --select option,
        otherwise does nothing. `none` prints no object definitions.
    """,
)
@click.option(
    "--select",
    multiple=True,
    type=str,
    help="""
        Print only matching object directives.
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
    "--limit",
    type=int,
    default=0,
    show_default=False,
    help="""
        Constrain the processing of object definitions to the given number, then exit.
    """,
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
    if opt["commit"]:
        # Replace original files with the transaction files, if any.
        return commit(config_files, opt)
    with contextlib.ExitStack() as exitmanager:
        update_mode = bool(opt["update"] or opt["delete"])

        if config_files:
            # Open the file streams and register them with the exitmanager, so
            # that they are properly closed (and in case of update buffers,
            # deleted) on exit.
            if update_mode and opt["write"] == "transaction":
                transaction_suffix = TRANSACTION_SUFFIX
            else:
                transaction_suffix = None
            config_files = [
                exitmanager.enter_context(
                    ConfigFile(
                        name,
                        encoding=opt["encoding"],
                        update_mode=update_mode,
                        delete_mode=opt["delete"],
                        transaction_suffix=transaction_suffix,
                        transaction_check=not opt["no_transaction_check"],
                    )
                )
                for name in itertools.chain.from_iterable(config_files)
            ]
            # Define an iterator over all the object definitions in the files.
            objdefs = itertools.chain.from_iterable(
                config_file.read_objects() for config_file in config_files
            )
        else:
            if update_mode:
                # Abort if the given options require named config files.
                raise click.ClickException(
                    "Unable to use --update, --delete without named config files."
                )
            # Read object definitions from stdin when no config files are
            # given.
            objdefs = ConfigStream(sys.stdin).read_objects()

        # Counter object for some basic analytics.
        counter = collections.Counter()
        # Counter object for the --count option
        if opt["count"]:
            groupcounter = collections.defaultdict(collections.Counter)
        # Get the list of all filter expressions registered via the various
        # options.
        registered_filters = FilterType.registered_filters

        # Get the set of selected object directives
        selected = opt["select"] or None

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
                elif opt["output"] == "oneline":
                    # Print a one-line representation of the object
                    # definition.
                    identifier = objdef.identifier
                    if identifier:
                        click.echo(
                            f"{objdef.objtype} '{identifier}' at {objdef.location}"
                        )
                    else:
                        click.echo(f"{objdef.objtype} at {objdef.location}")
                    if selected:
                        for k in selected:
                            v = objdef[k]
                            if v:
                                click.echo(f"    {k:{objdef.keywidth}} {v}")
                        click.echo()
                elif opt["output"] == "value":
                    if selected is None:
                        raise click.ClickException(
                            "Unable to use --output value without --select."
                        )
                    for k in selected:
                        v = objdef[k]
                        if v:
                            click.echo(v)
                elif opt["output"] == "naemon":
                    # Print metadata options.
                    if "filter" in opt["metadata"]:
                        for match in matches:
                            click.echo(f"# Filter: {match.expr}")
                    if "file" in opt["metadata"]:
                        click.echo(f"# File: {objdef.location}")
                    # Print the matched object definition.
                    click.echo(objdef.dumps(selected=selected))

                counter["matched"] += 1

                if opt["limit"] and counter["matched"] >= opt["limit"]:
                    break
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
        if "total" in opt["metadata"] and opt["output"] != "value":
            click.echo(
                f"# Total: {counter['matched']} / {counter['total']} "
                f"matching object definition(s)"
            )

        if update_mode:
            # Move updated files based on the --overwrite option.
            for config_file in config_files:
                if config_file.updated:
                    config_file.close()
                    if opt["write"] == "transaction":
                        shutil.move(
                            config_file.updated_name,
                            config_file.name + TRANSACTION_SUFFIX,
                        )
                    elif opt["write"] == "overwrite":
                        shutil.move(config_file.updated_name, config_file.name)
                    elif opt["write"] == "backup":
                        shutil.move(config_file.name, config_file.name + BACKUP_SUFFIX)
                        shutil.move(config_file.updated_name, config_file.name)


def commit(config_files, opt):
    for config_file in itertools.chain.from_iterable(config_files):
        try:
            if opt["no_transaction_check"] or os.path.getmtime(
                config_file
            ) < os.path.getmtime(f"{config_file}{TRANSACTION_SUFFIX}"):
                shutil.move(config_file + TRANSACTION_SUFFIX, config_file)
                click.echo(f"{config_file}{TRANSACTION_SUFFIX} -> {config_file}")
            else:
                click.echo(
                    f"Skipped: Original file newer than transaction file: {config_file}"
                )
        except FileNotFoundError:
            pass
