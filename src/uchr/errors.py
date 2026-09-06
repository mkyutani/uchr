class UchrError(Exception):
    """Base exception for uchr"""


class DownloadError(UchrError):
    """Exception for download-related errors"""


class ParseError(UchrError):
    """Exception for data parsing errors"""


class DatabaseError(UchrError):
    """Exception for database-related errors"""
