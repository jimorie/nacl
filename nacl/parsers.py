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
        register_name.set_registered(self.__class__)

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
            >>> obj = MyDataObject()
            >>> obj
            MyDataObject()

            >>> obj["foo"]
            42

            >>> obj["bar"] is None
            True

            >>> obj = MyDataObject({"foo": 1, "bar": 2})
            >>> obj
            MyDataObject([('foo', 1), ('bar', 2)])

            >>> obj["foo"]
            42

            >>> obj["bar"]
            2
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
        Parse a new `DataObject` from the lines in `source`. Otherwise same as
        `load`.

        Examples:

            >>> class MyDataObject(DataObject):
            ...     @classmethod
            ...     def load(cls, lines, source_file=None):
            ...         linenum, line = next(lines)
            ...         return cls(
            ...             [line.split("=")], linenum=linenum, source_file=source_file
            ...         )

            >>> MyDataObject.loads("foo=bar")
            MyDataObject([('foo', 'bar')])

            >>> MyDataObject.loads(
            ...     "foo=bar", source_file=DataFile("/dev/random")
            ... ).location
            '/dev/random line 1'

        """
        return cls.load(enumerate(source.splitlines(), 1), source_file=source_file)

    def dump(self, stream: t.TextIO, *args, **kwargs):
        """
        Write the string representation of this `DataObject` to `stream`.
        """
        raise NotImplementedError()

    def dumps(self, *args, **kwargs) -> str:
        """
        Return the string representation of this `DataObject` as a string.

        Examples:

            >>> class MyDataObject(DataObject):
            ...     def dump(self, stream, *args, **kwargs):
            ...         stream.write("foo")

            >>> MyDataObject().dumps()
            'foo'
        """
        stream = io.StringIO()
        self.dump(stream, *args, **kwargs)
        return stream.getvalue()

    def autoconvert(self, key: str, value: str) -> t.Any:
        """
        Hook for sub-classes to convert any value returned by `__getitem__`.
        """
        return value

    @property
    def location(self) -> str:
        """
        Return a reference to the source of this `DataClass`.

        Examples:

            >>> DataObject().location
            ''

            >>> DataObject(linenum=1).location
            'line 1'

            >>> DataObject(source_file=DataFile("/dev/random")).location
            '/dev/random'

            >>> DataObject(linenum=1, source_file=DataFile("/dev/random")).location
            '/dev/random line 1'
        """
        if self.source_file and self.linenum:
            return f"{self.source_file.name} line {self.linenum}"
        if self.linenum:
            return f"line {self.linenum}"
        if self.source_file:
            return self.source_file.name
        return ""

    def update(self, k: str, v: t.Any):
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

    Examples:

        >>> import io

        >>> class MyDataObject(DataObject):
        ...     @classmethod
        ...     def load(cls, lines, source_file=None):
        ...         linenum, line = next(lines)
        ...         return cls(
        ...             [line.split("=")], linenum=linenum, source_file=source_file
        ...         )
        ...     def dump(self, stream, *args, **kwargs):
        ...         stream.write("foo")

        >>> class MyDataStream(DataStream):
        ...     object_cls = MyDataObject

        >>> data = (
        ...     "foo=bar\\n"
        ...     "# This is a comment\\n"
        ...     "bar=foo # Yes, just foo\\n"
        ... )

        >>> list(MyDataStream(io.StringIO(data)).read_objects())
        [MyDataObject([('foo', 'bar')]), MyDataObject([('bar', 'foo')])]
    """

    object_cls: DataObject = None

    def __init__(self, stream: t.TextIO = None):
        self.stream = stream
        self.lines = self.read_lines(enumerate(stream, 1))

    def read_lines(self, lines: Lines) -> Lines:
        """
        Generate enumerated lines of non-empty data from the stream.
        """
        for linenum, line in lines:
            line = self.preprocess_line(line)
            if line:
                yield linenum, line

    def preprocess_line(self, line: str) -> str:
        """
        Strip all but non-comment data from `line` and return it. This can be
        overloaded by sub-classes that use different comment markers.
        """
        if "#" in line:
            line, _ = line.split("#", 1)
        return line.strip()

    def read_object(self) -> t.Optional[DataObject]:
        """
        Parse a single object instance of `object_cls` from the stream and
        return it, or `None` if no object could be parsed.
        """
        return self.object_cls.load(self.lines)

    def read_objects(self) -> t.Iterator[DataObject]:
        """
        Parse all object instances of `object_cls` from the stream, and yield
        them as they are ready.
        """
        while True:
            try:
                obj = self.read_object()
                if obj:
                    yield obj
            except StopIteration:
                break


class DataFile(DataStream):
    """
    A `DataStream` for files. If `update_mode` is True, a copy of the file is
    written as it's being read. Writing to the copy is buffered and can be
    intercepted by instances of `DataObject` to inject updated data instead.

    Examples:

        >>> class MyDataObject(DataObject):
        ...     @classmethod
        ...     def load(cls, lines, source_file=None):
        ...         while True:
        ...             linenum, line = next(lines)
        ...             if line.startswith("foo"):
        ...                 if source_file:
        ...                     source_file.handle_prefix()
        ...                 return cls(
        ...                     [line.split("=")],
        ...                     linenum=linenum,
        ...                     source_file=source_file,
        ...                 )
        ...     def dump(self, stream, **kwargs):
        ...         stream.write(",".join(f"{k}={v}" for k, v in self.items()))
        ...         stream.write("\\n")

        >>> class MyDataFile(DataFile):
        ...     object_cls = MyDataObject

        >>> import tempfile, os
        >>> mytempfile = tempfile.NamedTemporaryFile(delete=False)
        >>> try:
        ...     _ = mytempfile.write(b"bar=1\\nfoo=2\\nbar=3\\nfoo=4\\nbar=5")
        ...     mytempfile.close()
        ...     with MyDataFile(mytempfile.name) as datafile:
        ...         list(datafile.read_objects())
        ... finally:
        ...     os.remove(mytempfile.name)
        [MyDataObject([('foo', '2')]), MyDataObject([('foo', '4')])]

        >>> import tempfile, os
        >>> mytempfile = tempfile.NamedTemporaryFile(delete=False)
        >>> try:
        ...     _ = mytempfile.write(b"bar=1\\nfoo=2\\nbar=3\\nfoo=4\\nbar=5")
        ...     mytempfile.close()
        ...     with MyDataFile(mytempfile.name, update_mode=True) as datafile:
        ...         obj = datafile.read_object()
        ...         obj["foo"] = "42"
        ...         datafile.handle_update(obj)
        ...         objects = list(datafile.read_objects())
        ...         datafile.close()
        ...         with open(datafile.copystream.name, mode="rb") as fh:
        ...             datacopy = fh.read()
        ... finally:
        ...     os.remove(mytempfile.name)
        >>> obj
        MyDataObject([('foo', '42')])
        >>> objects
        [MyDataObject([('foo', '4')])]
        >>> datacopy
        b'bar=1\\nfoo=42\\nbar=3\\nfoo=4\\nbar=5'
    """

    def __init__(
        self,
        name: str,
        mode: str = "r",
        encoding: str = "utf-8",
        update_mode: bool = False,
        delete_mode: bool = False,
    ):
        super().__init__(open(name, mode=mode, encoding=encoding))
        self.encoding = encoding
        self.name = name
        self.update_mode = update_mode or delete_mode
        self.delete_mode = delete_mode
        if update_mode:
            self.copystream = tempfile.NamedTemporaryFile(
                mode="w", encoding=encoding, delete=False
            )
            self.copybuffer = []
            self.updated = False

    def read_object(self) -> t.Optional[DataObject]:
        """
        Parse a single object instance of `object_cls` from the stream and
        return it, initialized with ourselves as its `source_file`, or return
        `None` if no object could be parsed.
        """
        return self.object_cls.load(self.lines, source_file=self)

    def preprocess_line(self, line: str) -> str:
        """
        Strip all but non-comment data from `line` and return it. In
        `update_mode` the raw line is copied before it is processed.
        """
        if self.update_mode:
            self.copybuffer.append(line)
        return super().preprocess_line(line)

    def handle_prefix(self):
        """
        Flush all lines in the `copybuffer` -- except for the most recently
        buffered line. This can be called by `DataObject` parsers when they
        read the first line that is part of their definition, this will then
        flush all the junk lines read before it.
        """
        if self.update_mode and not self.delete_mode:
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

    def handle_update(self, obj: t.Optional[DataObject]):
        """
        Clear all lines in the `copybuffer`, discarding them to instead dump
        the definition of `obj` to the `copystream`. This can be called when a
        `DataObject` has been updated and should be written to file. If `obj`
        is `None` or the `DataFile` is in `delete_mode` the object definition
        will be removed instead of updated.
        """
        if self.delete_mode or obj is None:
            self.copybuffer.clear()
            self.updated = True
        elif self.update_mode:
            self.copybuffer.clear()
            obj.dump(self.copystream)
            self.updated = True

    @property
    def updated_name(self) -> str:
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
