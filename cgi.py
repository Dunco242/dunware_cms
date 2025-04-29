"""
Replacement for the removed cgi module in Python 3.13+
Place this file in your project root directory.
"""
from urllib.parse import parse_qs

def parse_multipart(fp, pdict):
    """
    Parse multipart/form-data input.

    This is a simplified implementation that returns data similar to
    the original cgi.parse_multipart function.
    """
    boundary = pdict.get('boundary', b'').decode('ascii')
    if not boundary:
        return {}

    content_length = int(pdict.get('content-length', -1))
    if content_length <= 0:
        return {}

    result = {}

    # Read all data
    try:
        data = fp.read(content_length)

        # Split by boundary
        parts = data.split(b'--' + boundary.encode('ascii'))

        # Process each part
        for part in parts[1:-1]:  # Skip first empty part and final boundary
            if not part or part == b'--\r\n':
                continue

            # Find headers end
            header_end = part.find(b'\r\n\r\n')
            if header_end == -1:
                continue

            headers_raw = part[:header_end].decode('latin1')
            body = part[header_end+4:]

            # Parse headers
            name = None
            for header in headers_raw.split('\r\n'):
                if header.lower().startswith('content-disposition:'):
                    # Extract name from content-disposition
                    for param in header.split(';'):
                        param = param.strip()
                        if param.startswith('name='):
                            name = param[5:].strip('"\'')
                            break

            if name:
                # Remove final \r\n if present
                if body.endswith(b'\r\n'):
                    body = body[:-2]

                # Add to result
                if name in result:
                    result[name].append(body)
                else:
                    result[name] = [body]
    except:
        # Return empty dict on any error
        pass

    return result

# Define a fake FieldStorage class if needed
class FieldStorage:
    def __init__(self, fp=None, headers=None, outerboundary=None,
                 environ=None, keep_blank_values=False, strict_parsing=False,
                 limit=None, encoding='utf-8', errors='replace', max_num_fields=None,
                 separator='&'):
        self.name = None
        self.filename = None
        self.list = []
        self.type = None
        self.file = None
        self.type_options = {}
        self.disposition = None
        self.disposition_options = {}
        self.headers = {}
        self.value = None

def escape(s, quote=False):
    """Replace special characters '&', '<' and '>' by SGML entities."""
    s = str(s)
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    if quote:
        s = s.replace('"', "&quot;")
    return s
