"""Stdlib client for Skylinee Vision AI; does not run or replace the detector."""
import argparse
import json
import mimetypes
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import uuid

MAX_UPLOAD = 15 * 1024 * 1024
MAX_RESPONSE = 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def origin(value):
    u = urlsplit(value.strip())
    if (u.scheme not in {'http', 'https'} or not u.hostname or u.username
            or u.password or u.query or u.fragment or u.path not in {'', '/'}):
        raise ValueError('SKYLINEE_VISION_URL must be an HTTP(S) origin without credentials or path')
    return value.strip().rstrip('/')


def output_url(base, path):
    if not isinstance(path, str) or not re.fullmatch(r'/outputs/[A-Za-z0-9_.-]+', path):
        raise ValueError('Invalid detector output path')
    return base + path


def detect(image_path, service_url):
    base = origin(service_url)
    path = Path(image_path).expanduser().resolve(strict=True)
    mime = mimetypes.guess_type(path.name)[0]
    if mime not in {'image/jpeg', 'image/png', 'image/webp'}:
        raise ValueError('Select a JPEG, PNG or WEBP image')
    with path.open('rb') as f:
        data = f.read(MAX_UPLOAD + 1)
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError('Image must contain 1 byte to 15 MiB')
    boundary = 'skylinee-' + uuid.uuid4().hex
    # Fixed upload filename prevents local names from altering MIME headers.
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="image{path.suffix.lower()}"\r\nContent-Type: {mime}\r\n\r\n').encode()
    body += data + f'\r\n--{boundary}--\r\n'.encode()
    request = Request(base + '/api/detect', data=body,
                      headers={'Content-Type': 'multipart/form-data; boundary=' + boundary}, method='POST')
    # Use the explicitly configured service directly; refuse redirects of image bytes.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=120) as response:
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError('Detector response exceeded limit')
    result = json.loads(raw)
    if (not isinstance(result, dict) or result.get('status') != 'ok'
            or not isinstance(result.get('detections'), list)
            or type(result.get('count')) is not int
            or result['count'] != len(result['detections'])):
        raise ValueError('Detector returned an invalid result')
    result['annotated_url'] = output_url(base, result.get('annotated_url'))
    for item in result['detections']:
        if not isinstance(item, dict):
            raise ValueError('Invalid detection entry')
        item['crop_url'] = output_url(base, item.get('crop_url'))
    return result


def main():
    parser = argparse.ArgumentParser(description='Run Skylinee object detection')
    parser.add_argument('--image', required=True)
    args = parser.parse_args()
    try:
        url = os.environ.get('SKYLINEE_VISION_URL', '')
        if not url:
            raise ValueError('Configure SKYLINEE_VISION_URL in the Hermes runtime')
        result = detect(args.image, url)
    except HTTPError as exc:
        print(json.dumps({'status': 'error', 'error': 'Detector HTTP failure', 'http_status': exc.code}))
        return 1
    except (ValueError, OSError, URLError):
        print(json.dumps({'status': 'error', 'error': 'Detection failed: check image, service URL and connectivity'}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
