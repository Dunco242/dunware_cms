"""
Compatibility module for the removed cgi module.
Place this in your project root to handle imports from packages still using cgi.
"""
from urllib.parse import parse_qs as _parse_qs

# Common functions from the old cgi module
def parse_qs(qs, keep_blank_values=False, strict_parsing=False, encoding='utf-8', errors='replace'):
    """Parse a query string."""
    return _parse_qs(qs, keep_blank_values=keep_blank_values,
                    strict_parsing=strict_parsing, encoding=encoding, errors=errors)

# Other functions that might be needed
def escape(s, quote=False):
    """Replace special characters '&', '<' and '>' by SGML entities."""
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    if quote:
        s = s.replace('"', "&quot;")
    return s

# Dummy FieldStorage class - extend as needed
class FieldStorage:
    def __init__(self, *args, **kwargs):
        self.list = []
        self.file = None
        self.type = None
        self.type_options = {}
        self.disposition = None
        self.disposition_options = {}
        self.headers = {}
        self.name = None
        self.filename = None
        self.value = None
