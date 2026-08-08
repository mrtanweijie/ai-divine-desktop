from .notes import NotesAdapter  # noqa: F401
from .presentation import PresentationAdapter  # noqa: F401
from .read_file import ReadFileAdapter  # noqa: F401
from .read_image import ReadImageAdapter  # noqa: F401
from .search_files import SearchFilesAdapter  # noqa: F401
from .spreadsheet import SpreadsheetAdapter  # noqa: F401
from .terminal import TerminalAdapter  # noqa: F401
from .web_fetch import WebFetchAdapter  # noqa: F401
from .word_document import WordDocumentAdapter  # noqa: F401

from ..registry import register_tool  # noqa: E402


_ = register_tool
