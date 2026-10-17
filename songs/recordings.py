"""Public audio delivery with byte-range support for browser seeking."""
import re

from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_safe

from .models import Recording

@require_safe
def recording(request, pk):
    item = get_object_or_404(Recording, pk=pk)
    if not item.file.storage.exists(item.file.name):
        raise Http404('Recording not found')
    size = item.size
    etag = f'"{item.pk}-{size}"'
    if request.headers.get('If-None-Match') == etag:
        response = HttpResponse(status=304)
    else:
        requested_range = request.headers.get('Range')
        if request.headers.get('If-Range') not in (None, etag):
            requested_range = None
        start, end = 0, size - 1
        if requested_range:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested_range)
            try:
                if not match or not any(match.groups()): raise ValueError
                first, last = match.groups()
                if first:
                    start = int(first)
                    end = min(int(last), size-1) if last else size-1
                else:
                    length = int(last)
                    if length <= 0: raise ValueError
                    start = max(0, size-length)
                if start >= size or start > end: raise ValueError
            except ValueError:
                response = HttpResponse(status=416)
                response['Content-Range'] = f'bytes */{size}'
                response['Accept-Ranges'] = 'bytes'
                return response
        status = 206 if requested_range else 200
        if request.method == 'HEAD':
            response = HttpResponse(status=status, content_type=item.media_type)
        elif requested_range:
            def chunks():
                with item.file.storage.open(item.file.name, 'rb') as source:
                    source.seek(start)
                    remaining = end-start+1
                    while remaining > 0:
                        chunk = source.read(min(64*1024, remaining))
                        if not chunk: break
                        remaining -= len(chunk)
                        yield chunk
            response = StreamingHttpResponse(chunks(), status=status, content_type=item.media_type)
        else:
            response = FileResponse(item.file.open('rb'), content_type=item.media_type)
        response['Content-Length'] = str(end-start+1)
        if requested_range:
            response['Content-Range'] = f'bytes {start}-{end}/{size}'
        # Use a generated filename: no uploader-supplied text goes into response headers.
        suffix = item.file.name.rsplit('.', 1)[-1]
        response['Content-Disposition'] = content_disposition_header(False, f'recording-{item.pk}.{suffix}')
    response['ETag'] = etag
    response['Accept-Ranges'] = 'bytes'
    response['Cache-Control'] = 'public, max-age=3600'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "default-src 'none'"
    return response
