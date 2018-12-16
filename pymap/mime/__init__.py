
from abc import abstractmethod, ABCMeta
from email.headerregistry import ContentTypeHeader
from email.policy import SMTP
from itertools import chain, islice
from typing import Optional, Tuple, Iterable, Sequence, Mapping, List, Dict
from typing_extensions import Final

from .parsed import ParsedHeaders
from ._util import whitespace, find_any, get_raw

__all__ = ['MessageContent', 'MessageHeader', 'MessageBody']

_default_type: Final[ContentTypeHeader] = (  # type: ignore
    SMTP.header_fetch_parse('Content-Type', 'text/plain'))

_Line = Tuple[int, int, int]
_Lines = Sequence[_Line]
_Headers = Mapping[bytes, Sequence[Sequence[memoryview]]]
_Folded = Sequence[Tuple[bytes, memoryview]]


class MessageContent:
    """Contains the message content, parsed for IMAP processing.

    Attributes:
        raw: The full message buffer, including headers and body.
        lines: The number of lines in the message content.
        header: The message header.
        body: The message body.

    """

    __slots__ = ['raw', 'lines', 'header', 'body']

    def __init__(self, raw: memoryview, lines: int,
                 header: 'MessageHeader', body: 'MessageBody') -> None:
        super().__init__()
        self.raw: Final = raw
        self.lines: Final = lines
        self.header: Final = header
        self.body: Final = body

    def walk(self) -> Iterable['MessageContent']:
        """Iterate through the message and all its nested sub-parts in the
        order they occur.

        """
        if self.body.has_nested:
            return chain([self], *(part.walk() for part in self.body.nested))
        else:
            return [self]

    @classmethod
    def parse(cls, data: bytes) -> 'MessageContent':
        """Parse the bytestring into message content.

        Args:
            data: The bytestring to parse.

        """
        lines = cls._find_lines(data)
        return cls._parse(data, lines)

    @classmethod
    def _parse(cls, data: bytes, lines: _Lines) -> 'MessageContent':
        header_lines, body_lines = cls._split_lines(data, lines)
        header = MessageHeader._parse(data, header_lines)
        content_type = header.parsed.content_type
        body = MessageBody._parse(data, body_lines, content_type)
        raw = get_raw(data, header_lines, body_lines)
        num_lines = len(lines) - 1
        return cls(raw, num_lines, header, body)

    @classmethod
    def _find_lines(cls, data: bytes) -> _Lines:
        start = 0
        end = len(data)
        ret: List[_Line] = []
        while True:
            idx = data.find(b'\n', start, end)
            if idx < 0:
                ret.append((start, end, end))
                break
            next_start = idx + 1
            idx_minus_1 = idx - 1
            if idx_minus_1 >= start and data[idx_minus_1] == 0x0d:
                idx = idx_minus_1
            ret.append((start, idx, next_start))
            start = next_start
        return ret

    @classmethod
    def _split_lines(cls, data: bytes, lines: _Lines) -> Tuple[_Lines, _Lines]:
        for i, line in enumerate(lines):
            start, end, _ = line
            ws_end = find_any(data, whitespace, start, end, False, False)
            if ws_end < 0:
                return lines[0:i + 1], lines[i + 1:]
        return [], lines


class MessageHeader:
    """The message header. Contains lines in the form of ``Header: value\\n``,
    possibly folded onto multiple lines where subsequent lines start with
    whitespace.

    Attributes:
        raw: The message header buffer.
        lines: The number of lines in the message header.
        folded: A list of headers, as they occurred in the original data, as
            tuples of the lower-cased header name and the full header value,
            including the header name and any extra folded lines.
        parsed: The message headers, as a dictionary-like object that parses
            headers on-demand.

    """

    __slots__ = ['raw', 'lines', 'folded', 'parsed']

    def __init__(self, raw: memoryview, lines: int, folded: _Folded,
                 parsed: ParsedHeaders) -> None:
        super().__init__()
        self.raw: Final = raw
        self.lines: Final = lines
        self.folded: Final = folded
        self.parsed: Final = parsed

    @classmethod
    def _parse(cls, data: bytes, lines: _Lines) -> 'MessageHeader':
        folds = cls._find_folds(data, lines)
        folded, parsed = cls._parse_headers(data, folds)
        raw = get_raw(data, lines)
        return cls(raw, len(lines), folded, parsed)

    @classmethod
    def _find_folds(cls, data: bytes, lines: _Lines) -> Sequence[_Lines]:
        ret: List[List[Tuple[int, int, int]]] = []
        if not lines:
            return []
        for line in islice(lines, len(lines) - 1):
            start, end, _ = line
            length = end - start
            if length >= 1 and data[start] in whitespace:
                if ret:
                    ret[-1].append(line)
            else:
                ret.append([line])
        return ret

    @classmethod
    def _parse_headers(cls, data: bytes, folds: Sequence[_Lines]) \
            -> Tuple[_Folded, ParsedHeaders]:
        headers: Dict[bytes, List[List[memoryview]]] = {}
        folded: List[Tuple[bytes, memoryview]] = []
        view = memoryview(data)
        for group in folds:
            start, end, _ = group[0]
            colon = data.find(b':', start, end)
            if colon < 0:
                continue
            name = data[start:colon].strip().lower()
            values = headers.setdefault(name, [])
            values.append([view[start:end] for start, end, _ in group])
            folded.append((name, get_raw(data, group)))
        return folded, ParsedHeaders(headers)

    @classmethod
    def _join_group(cls, data: bytes, group: _Lines, colon: int) -> bytes:
        first_start, first_end, _ = group[0]
        value_offset = colon - first_start + 1
        length = sum(end - start for start, end, _ in group)
        ret = bytearray(length - value_offset)
        current = first_end - value_offset
        ret[0:current] = data[colon + 1:first_end]
        for start, end, _ in islice(group, 1, None):
            current_end = current + (end - start)
            ret[current:current_end] = data[start:end]
            current = current_end
        return bytes(ret)


class MessageBody(metaclass=ABCMeta):
    """The message body, starting immediately after the header. The body may
    contain nested sub-parts, which are each valid :class:`MessageContent`
    objects.

    Attributes:
        raw: The message body buffer.
        lines: The number of lines in the message body.
        content_type: The content type of the message body.

    """

    __slots__ = ['raw', 'lines', 'content_type']

    def __init__(self, raw: memoryview, lines: int,
                 content_type: ContentTypeHeader) -> None:
        super().__init__()
        self.raw: Final = raw
        self.lines: Final = lines
        self.content_type: Final = content_type

    @property
    @abstractmethod
    def has_nested(self) -> bool:
        """True if the message body is composed of nested sub-parts."""
        ...

    @property
    @abstractmethod
    def nested(self) -> Sequence[MessageContent]:
        """If :attr:`.has_nested` is True, contains the list of sub-parts."""
        ...

    @classmethod
    def _parse(cls, data: bytes, lines: _Lines,
               content_type: Optional[ContentTypeHeader]) -> 'MessageBody':
        if content_type is None:
            content_type = _default_type
        maintype = content_type.maintype
        if maintype == 'multipart':
            boundary = cls._get_boundary(content_type)
            if boundary:
                return _MultipartBody._parse_body(
                    data, lines, content_type, boundary)
        elif maintype == 'message' and content_type.subtype == 'rfc822':
            return _RFC822Body._parse_body(data, lines, content_type)
        return _SinglepartBody._parse_body(data, lines, content_type)

    @classmethod
    def _get_boundary(cls, content_type: ContentTypeHeader) -> Optional[bytes]:
        try:
            boundary = content_type.params['boundary']
        except KeyError:
            pass
        else:
            if boundary:
                try:
                    return boundary.encode('ascii')
                except UnicodeError:
                    pass
        return None


class _MultipartBody(MessageBody):

    __slots__ = ['_nested']

    def __init__(self, raw: memoryview, lines: int,
                 content_type: ContentTypeHeader,
                 nested: Sequence[MessageContent]) -> None:
        super().__init__(raw, lines, content_type)
        self._nested = nested

    @property
    def has_nested(self) -> bool:
        return True

    @property
    def nested(self) -> Sequence[MessageContent]:
        return self._nested

    @classmethod
    def _parse_body(cls, data: bytes, lines: _Lines,
                    content_type: ContentTypeHeader, boundary: bytes) \
            -> '_MultipartBody':
        parts = cls._find_parts(data, lines, boundary)
        nested: List[MessageContent] = []
        for part_lines in parts:
            sub_content = MessageContent._parse(data, part_lines)
            nested.append(sub_content)
        raw = get_raw(data, lines)
        return cls(raw, len(lines), content_type, nested)

    @classmethod
    def _find_parts(cls, data: bytes, lines: _Lines, boundary: bytes) \
            -> Sequence[_Lines]:
        ret: List[List[_Line]] = []
        view = memoryview(data)
        part_match = (b'--%s' % boundary, b'--%s' % boundary)
        stop_match = (b'--%s--' % boundary, b'--%s--' % boundary)
        for line in lines:
            start, end, _ = line
            line_view = view[start:end]
            if any(line_view == m for m in stop_match):
                break
            elif any(line_view == m for m in part_match):
                ret.append([])
            elif ret:
                ret[-1].append(line)
        return ret


class _RFC822Body(MessageBody):

    __slots__ = ['_nested']

    def __init__(self, subpart: MessageContent,
                 content_type: ContentTypeHeader) -> None:
        super().__init__(subpart.raw, subpart.lines, content_type)
        self._nested: Sequence[MessageContent] = [subpart]

    @property
    def has_nested(self) -> bool:
        return True

    @property
    def nested(self) -> Sequence[MessageContent]:
        return self._nested

    @classmethod
    def _parse_body(cls, data: bytes, lines: _Lines,
                    content_type: ContentTypeHeader) -> '_RFC822Body':
        subpart = MessageContent._parse(data, lines)
        return cls(subpart, content_type)


class _SinglepartBody(MessageBody):

    def __init__(self, raw: memoryview, lines: int,
                 content_type: ContentTypeHeader) -> None:
        super().__init__(raw, lines, content_type)

    @property
    def has_nested(self) -> bool:
        return False

    @property
    def nested(self) -> Sequence[MessageContent]:
        return []

    @classmethod
    def _parse_body(cls, data: bytes, lines: _Lines,
                    content_type: ContentTypeHeader) -> '_SinglepartBody':
        raw = get_raw(data, lines)
        return cls(raw, len(lines), content_type)