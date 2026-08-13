from .calculator import CalculatorAdapter  # noqa: F401
from .clipboard import ClipboardAdapter  # noqa: F401
from .create_plan import CreatePlanAdapter  # noqa: F401
from .describe_svg import DescribeSvgAdapter  # noqa: F401
from .directory_tree import DirectoryTreeAdapter  # noqa: F401
from .draw_svg import DrawSvgAdapter  # noqa: F401
from .edit_files import EditFilesAdapter  # noqa: F401
from .edit_svg import EditSvgAdapter  # noqa: F401
from .generate_chart import GenerateChartAdapter  # noqa: F401
from .github_skill import (  # noqa: F401
    InstallSkillAdapter,
    PreviewSkillRepoAdapter,
)
from .image_resize import ImageResizeAdapter  # noqa: F401
from .mermaid_export import MermaidExportAdapter  # noqa: F401
from .notes import NotesAdapter  # noqa: F401
from .pdf_split_merge import PdfSplitMergeAdapter  # noqa: F401
from .presentation import PresentationAdapter  # noqa: F401
from .rag_index import RagIndexAdapter  # noqa: F401
from .rag_search import RagSearchAdapter  # noqa: F401
from .read_file import ReadFileAdapter  # noqa: F401
from .read_image import ReadImageAdapter  # noqa: F401
from .schedule_task import ScheduleTaskAdapter  # noqa: F401
from .search_files import SearchFilesAdapter  # noqa: F401
from .skill_migration import (  # noqa: F401
    DiscoverImportableSkillsAdapter,
    MigrateSkillAdapter,
)
from .sqlite_query import SqliteQueryAdapter  # noqa: F401
from .spreadsheet import SpreadsheetAdapter  # noqa: F401
from .svg_to_png import SvgToPngAdapter  # noqa: F401
from .svg_to_png_batch import SvgToPngBatchAdapter  # noqa: F401
from .terminal import TerminalAdapter  # noqa: F401
from .ux_html import UxHtmlAdapter  # noqa: F401
from .web_fetch import WebFetchAdapter  # noqa: F401
from .web_fetch_batch import WebFetchBatchAdapter  # noqa: F401
from .write_calendar import WriteCalendarAdapter  # noqa: F401
from .write_file import WriteFileAdapter  # noqa: F401
from .word_document import WordDocumentAdapter  # noqa: F401

from ..registry import register_tool  # noqa: E402


_ = register_tool
