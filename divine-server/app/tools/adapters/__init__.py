from .notes import NotesAdapter  # noqa: F401
from .read_file import ReadFileAdapter  # noqa: F401
from .read_image import ReadImageAdapter  # noqa: F401
from .spreadsheet import SpreadsheetAdapter  # noqa: F401
from .word_document import WordDocumentAdapter  # noqa: F401

from ..registry import register_tool  # noqa: E402


_ = register_tool
