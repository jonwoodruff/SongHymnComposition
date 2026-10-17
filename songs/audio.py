"""Validated public recordings, stored outside the source tree's tracked files."""
from pathlib import Path
import math
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from mutagen import File, MutagenError
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.wave import WAVE
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus
from mutagen.flac import FLAC

FORMATS = {
    '.mp3': ((MP3,), 'audio/mpeg'),
    '.m4a': ((MP4,), 'audio/mp4'),
    '.wav': ((WAVE,), 'audio/wav'),
    '.ogg': ((OggVorbis, OggOpus), 'audio/ogg'),
    '.flac': ((FLAC,), 'audio/flac'),
}

def recording_path(instance, filename):
    return f'recordings/{instance.song_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}'

def validate_audio(upload):
    suffix = Path(upload.name).suffix.lower()
    if suffix not in FORMATS:
        raise ValidationError('Choose an MP3, M4A, WAV, OGG, or FLAC recording.')
    if not upload.size or upload.size > settings.AUDIO_UPLOAD_MAX_BYTES:
        raise ValidationError('Recordings must be non-empty and no larger than 25 MB.')
    classes, mime = FORMATS[suffix]
    try:
        upload.seek(0)
        parsed = File(upload, options=list(classes))
        duration = getattr(getattr(parsed, 'info', None), 'length', 0)
        valid = isinstance(parsed, classes) and math.isfinite(duration) and duration > 0
    except (MutagenError, ValueError, OSError, EOFError, OverflowError):
        valid = False
    finally:
        upload.seek(0)
    if not valid:
        raise ValidationError('This file could not be read as a valid recording in the selected format.')
    return mime


def store_recording(upload, song, user, pending_files):
    from .models import Recording
    mime = validate_audio(upload)
    recording = Recording(song=song, uploader=user, media_type=mime,
                          original_name=Path(upload.name).name[:200], size=upload.size)
    recording.file.save(upload.name, upload, save=False)
    pending_files.append((recording.file.storage, recording.file.name))
    recording.save()
    return recording
