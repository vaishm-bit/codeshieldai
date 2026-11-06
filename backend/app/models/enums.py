"""Enumerations shared by models, schemas and services."""

import enum


class ScanStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SourceType(str, enum.Enum):
    PASTE = "paste"
    UPLOAD = "upload"


class Severity(str, enum.Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class ScannerTool(str, enum.Enum):
    BANDIT = "bandit"
    SEMGREP = "semgrep"


class VulnCategory(str, enum.Enum):
    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    HARDCODED_CREDENTIALS = "hardcoded_credentials"
    COMMAND_INJECTION = "command_injection"
    INSECURE_AUTHENTICATION = "insecure_authentication"
    INSECURE_CRYPTOGRAPHY = "insecure_cryptography"
    PATH_TRAVERSAL = "path_traversal"
    OTHER = "other"
