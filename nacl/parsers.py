""" Generic classes for parsing data objects from a stream of lines. """

import collections
import io
import os
import tempfile
import typing as t

from nacl.typing import Lines
from nacl.util import register_decorator


class register_name(register_decorator):
    """
    Decorator to define special property items of a `DataClass`. These items
    are accessible via `__getitem__`, but cannot be set.
    """

    pass


class DataObject(collections.OrderedDict):
    """
    Base class for dict-like objects that can be read from and written to a
    stream. The `load` and `dump` methods must be implemented by the
    sub-class.
    """

    def __init__(
        self,
        *args,
        linenum: int = 0,
        source_file: "DataFile" = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.linenum = linenum
        self.source_file = source_file

    def __new__(cls, *args, **kwargs):
        """
        Set the dict of registered names on the created instance before
        returning it.
        """
        register_name.set_registered(cls)
        return super().__new__(cls, *args, **kwargs)

    def __getitem__(self, key: t.Any) -> t.Any:
        """
        Return the value associated with `key`. Keys in our `register_name`
        dict are prioritized over our own underlying `OrderedDict`. Missing
        keys do not raise `KeyError` but instead return `None`.

        Examples:

            >>> class MyDataObject(DataObject):
            ...     @register_name
            ...     def foo(self):
            ...         return 42
            >>> obj = MyDataObject({"foo": 1, "bar": 2})
            >>> obj
            MyDataObject([('foo', 1), ('bar', 2)])

            >>> obj["foo"]
            42

            >>> obj["bar"]
            2

            >>> obj["foobar"] is None
            True
        """
        try:
            if key in self.register_name:
                return self.register_name[key](self)
            return self.autoconvert(key, super().__getitem__(key))
        except KeyError:
            return None

    @classmethod
    def load(cls, lines: Lines, source_file: "DataFile" = None) -> "DataObject":
        """
        Parse a new `DataObject` from the stream `lines`. The `source_file`
        argument can be given to remember the file path it was read from.
        """
        raise NotImplementedError()

    @classmethod
    def loads(cls, source: str, source_file: "DataFile" = None) -> "DataObject":
        """
        Parse a new `DataObject` from the string `source`. Otherwise same as
        `load`.
        """
        return cls.load(io.StringIO(source), source_file=source_file)

    def dump(self, stream: t.TextIO):
        """
        Write the string representation of this `DataObject` to `stream`.
        """
        raise NotImplementedError()

    def dumps(self) -> str:
        """
        Return the string representation of this `DataObject` as a string.
        """
        stream = io.StringIO()
        self.dump(stream)
        return stream.getvalue()

    def autoconvert(self, key: t.Any, value: str) -> t.Any:
        """
        Hook for sub-classes to convert any value returned by `__getitem__`.
        """
        return value

    @property
    def location(self) -> str:
        """
        Return a reference to the source of this `DataClass`.
        """
        if self.source_file and self.linenum:
            return f"{self.source_file.name} line {self.linenum}"
        if self.linenum:
            return f"line {self.linenum}"
        if self.source_file:
            return self.source_file.name
        return ""

    def update(self, k, v):
        """
        Update the value of `k` with `v` in the underlying `OrderedDict`. A
        `v` equal to `None` or `""` will remove the key entirely.

        Examples:

            >>> obj = DataObject({"foo": 1})
            >>> obj
            DataObject([('foo', 1)])

            >>> obj.update("bar", 2)
            >>> obj
            DataObject([('foo', 1), ('bar', 2)])

            >>> obj.update("foo", "")
            >>> obj
            DataObject([('bar', 2)])
        """
        if (v is None or v == "") and k in self:
            del self[k]
        else:
            self[k] = v


class DataStream:
    """
    Base class for a stream from which `DataObject` instances can be read.
    Sub-classes must define the class variable `object_cls` as a class that
    implements the `DataObject` interface.
    """

    object_cls: DataObject = None

    def __init__(self, stream: t.TextIO = None):
        self.stream = stream

    def read_objects(self) -> t.Iterator[DataObject]:
        """
        Parse all object instances of `object_cls` from the stream, and yield
        them as they are ready.
        """
        lines = self.read_data_lines()
        while True:
            try:
                obj = self.read_object(lines)
                if obj:
                    yield obj
            except StopIteration:
                break

    def read_object(self, lines: Lines) -> t.Optional[DataObject]:
        """
        Parse a single object instance of `object_cls` from the stream and
        return it, or `None` if no object could be parsed.
        """
        return self.object_cls.load(lines)

    def read_data_lines(self) -> Lines:
        """
        Generate enumerated lines of non-comment data from the stream.
        """
        for linenum, line in enumerate(self.stream, 1):
            line = self.process_raw_line(line)
            if line:
                yield linenum, line

    def process_raw_line(self, line: str) -> str:
        """
        Strip all but non-comment data from `line` and return it. This can be
        overloaded by sub-classes that use different comment markers.
        """
        if "#" in line:
            line, _ = line.split("#", 1)
        return line.strip()


class DataFile(DataStream):
    """
    A `DataStream` for files. If `update_mode` is True a copy of the file is
    written as it's being read. Writing to the copy is buffered and can be
    intercepted by instances of `DataObject` to inject updated data instead.
    """

    def __init__(self, name: str, encoding: str = "utf-8", update_mode: bool = False):
        super().__init__(open(name, "r", encoding=encoding))
        self.encoding = encoding
        self.name = name
        self.update_mode = update_mode
        if update_mode:
            self.copystream = tempfile.NamedTemporaryFile(
                mode="w", encoding=encoding, delete=False
            )
            self.copybuffer = []
            self.updated = False

    def read_object(self, lines: Lines) -> t.Optional[DataObject]:
        """
        Parse a single object instance of `object_cls` from the stream and
        return it, initialized with ourselves as its `source_file`, or return
        `None` if no object could be parsed.
        """
        return self.object_cls.load(lines, self)

    def process_raw_line(self, line: str) -> str:
        """
        Strip all but non-comment data from `line` and return it. In
        `update_mode` the raw line is copied before it is processed.
        """
        if self.update_mode:
            self.copybuffer.append(line)
        return super().process_raw_line(line)

    def handle_prefix(self):
        """
        Flush all lines in the `copybuffer` -- except for the most recently
        buffered line. This can be called by `DataObject` parsers when they
        read the first line that is part of their definition, this will then
        flush all the junk lines read before it.
        """
        if self.update_mode:
            self.copystream.write("".join(self.copybuffer[:-1]))
            del self.copybuffer[:-1]

    def handle_unchanged(self):
        """
        Flush all lines in the `copybuffer`, copying them to the `copystream`.
        This can be called when a complete `DataObject` has been parsed, but
        does not require updates.
        """
        if self.update_mode:
            self.copystream.write("".join(self.copybuffer))
            self.copybuffer.clear()

    def handle_update(self, obj: DataObject):
        """
        Clear all lines in the `copybuffer`, discarding them to instead dump
        the definition of `obj` to the `copystream`. This can be called when
        a `DataObject` has been updated and should be written to file.
        """
        if self.update_mode:
            self.copybuffer.clear()
            obj.dump(self.copystream)
            self.updated = True

    @property
    def updated_name(self):
        """
        Return the temporary file name of our `copystream`.
        """
        return self.copystream.name if self.update_mode else None

    def close(self):
        """
        Close the file handles of both the original file and the updated file.
        """
        if self.update_mode:
            try:
                self.handle_unchanged()
                self.copystream.close()
            except ValueError:
                # File already closed
                pass
        return self.stream.close()

    def __enter__(self):
        """
        Actions when entering a `with` block.
        """
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Actions when exiting a `with` block.
        """
        self.close()
        if self.update_mode:
            try:
                os.remove(self.copystream.name)
            except FileNotFoundError:
                pass
