import io
from pathlib import Path
import tempfile
import uuid
import wave
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import Membership, Song, Part, Recording, Revision
from .policy import AGREEMENT_VERSION
from .workflow import act


def wave_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b'\x00\x00' * 8000)
    return buffer.getvalue()


def upload(name='melody.wav', data=None, content_type='audio/wav'):
    return SimpleUploadedFile(name, wave_bytes() if data is None else data, content_type=content_type)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RecordingTests(TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory(prefix='songhymn-recording-test-')
        self.addCleanup(self.storage.cleanup)
        settings = override_settings(MEDIA_ROOT=self.storage.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.author = self.member('author', 'contributor')
        self.reviewer = self.member('reviewer', 'reviewer')
        self.commenter = self.member('commenter', 'commenter')
        self.pending = self.member('pending', 'pending')
        self.song = Song.objects.create(title='Recorded song', author=self.author)
        for kind in ('concept', 'lyrics', 'tune'):
            Part.objects.create(song=self.song, kind=kind, content='First version', license_code='CC-BY-4.0')

    def member(self, name, role):
        user = User.objects.create_user(name, password='test-only-password')
        Membership.objects.create(user=user, role=role, agreement_version=AGREEMENT_VERSION,
                                  agreement_accepted_at=timezone.now())
        return user

    def post(self, action='recording', user=None, **changes):
        self.client.force_login(user or self.author)
        self.song.refresh_from_db()
        data = {'action': action, 'scope': 'tune', 'stage': self.song.stage,
                'song_revision': str(self.song.revision),
                'revision': str(self.song.parts.get(kind='tune').revision)}
        if action == 'recording': data['recording'] = upload()
        data.update(changes)
        return self.client.post(f'/songs/{self.song.pk}/', data, HTTP_ACCEPT='application/json')

    def test_tune_upload_is_publicly_playable_and_advances_revision(self):
        act(self.reviewer, self.song.pk, 'approve', {'scope':'tune', 'song_revision':'1'})
        self.song.author_signed = True
        self.song.save()
        response = self.post()
        self.assertEqual(response.status_code, 200)
        tune = self.song.parts.get(kind='tune')
        self.assertEqual(tune.revision, 2)
        self.assertEqual(tune.recording.media_type, 'audio/wav')
        self.assertEqual(tune.history.get(number=2).recording_id, tune.recording_id)
        self.song.refresh_from_db()
        self.assertFalse(self.song.author_signed)
        self.assertEqual(self.song.revision, 2)
        self.assertEqual(next(p for p in response.json()['parts'] if p['kind']=='tune')['approvals'], 0)
        self.client.logout()
        playback = self.client.get(tune.recording.get_absolute_url())
        self.assertEqual(playback.status_code, 200)
        self.assertEqual(playback['Content-Type'], 'audio/wav')
        self.assertEqual(b''.join(playback.streaming_content), wave_bytes())
        self.assertEqual(playback['X-Content-Type-Options'], 'nosniff')

    def test_replacement_and_removal_keep_historical_audio(self):
        self.assertEqual(self.post().status_code, 200)
        first = self.song.parts.get(kind='tune').recording
        self.assertEqual(self.post(recording=upload('replacement.wav')).status_code, 200)
        tune = self.song.parts.get(kind='tune')
        second = tune.recording
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(tune.history.get(number=2).recording_id, first.pk)
        self.assertEqual(self.post(action='remove_recording').status_code, 200)
        tune.refresh_from_db()
        self.assertIsNone(tune.recording_id)
        self.assertEqual(tune.history.get(number=3).recording_id, second.pk)
        self.assertTrue(first.file.storage.exists(first.file.name))
        self.assertEqual(self.client.head(first.get_absolute_url()).status_code, 200)

    def test_notation_edits_preserve_recording_and_snapshot(self):
        self.post()
        tune = self.song.parts.get(kind='tune')
        response = self.post(action='autosave', content='X:1\nK:C\nC D E F|')
        self.assertEqual(response.status_code, 200)
        tune.refresh_from_db()
        self.assertEqual(tune.history.get(number=3).recording_id, tune.recording_id)

    def test_permissions_pending_users_and_frozen_stage(self):
        self.assertEqual(self.post(user=self.commenter).status_code, 403)
        self.assertEqual(self.post(user=self.pending).status_code, 403)
        self.song.stage = 'frozen'
        self.song.save()
        self.assertEqual(self.post().status_code, 403)
        self.assertEqual(self.post(user=self.reviewer).status_code, 200)
        self.song.stage = 'published'
        self.song.save()
        self.assertEqual(self.post(user=self.reviewer).status_code, 403)
        self.assertEqual(Recording.objects.count(), 1)

    def test_stale_revisions_and_other_editor_leave_no_files(self):
        act(self.reviewer, self.song.pk, 'lock', {'scope':'tune','stage':'draft'})
        self.assertEqual(self.post().status_code, 409)
        self.assertEqual(Recording.objects.count(), 0)
        self.assertEqual(list(Path(self.storage.name).rglob('*')), [])
        from .models import EditLock
        EditLock.objects.all().delete()
        self.assertEqual(self.post(revision='0').status_code, 409)
        self.assertEqual(self.post(stage='frozen').status_code, 409)
        self.assertEqual(Recording.objects.count(), 0)

    def test_invalid_files_and_forged_extensions_are_rejected(self):
        for file in (upload('bad.wav', b'<script>bad</script>'),
                     upload('not-a-wave.mp3'), upload('bad.html'), upload('empty.wav', b'')):
            with self.subTest(name=file.name):
                self.assertEqual(self.post(recording=file).status_code, 409)
        self.assertEqual(Recording.objects.count(), 0)
        self.assertEqual(list(Path(self.storage.name).rglob('*')), [])

    @override_settings(AUDIO_UPLOAD_MAX_BYTES=100)
    def test_size_limit_is_checked_on_server(self):
        response = self.post()
        self.assertEqual(response.status_code, 409)
        self.assertIn('25 MB', response.json()['error'])
        self.assertFalse(Recording.objects.exists())

    def test_browser_supplied_mime_does_not_determine_response_type(self):
        response = self.post(recording=upload(content_type='text/html'))
        self.assertEqual(response.status_code, 200)
        recording = Recording.objects.get()
        self.assertEqual(recording.media_type, 'audio/wav')
        self.assertEqual(self.client.head(recording.get_absolute_url())['Content-Type'], 'audio/wav')

    def test_rollback_cleans_up_stored_file(self):
        with patch('songs.workflow.Revision.objects.create', side_effect=RuntimeError('Test failure')):
            with self.assertRaises(RuntimeError): self.post()
        self.assertEqual(Recording.objects.count(), 0)
        self.assertEqual([p for p in Path(self.storage.name).rglob('*') if p.is_file()], [])

    def test_audio_only_comments_do_not_change_song_revision(self):
        response = self.post(action='comment', user=self.commenter, body='', anchor='First', part_revision='1', recording=upload('suggestion.wav'))
        self.assertEqual(response.status_code, 200)
        comment = self.song.comments.get()
        self.assertEqual(comment.user, self.commenter)
        self.assertEqual(comment.anchor, 'First')
        self.assertTrue(comment.recording_id)
        self.assertIn('<audio', response.json()['comments_html'])
        self.assertNotIn('CC BY', response.json()['comments_html'])
        self.song.refresh_from_db()
        self.assertEqual(self.song.revision, 1)

    def test_comment_with_text_and_audio_and_failed_comment(self):
        response = self.post(action='comment', user=self.commenter, body='Try this ending', recording=upload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.song.comments.get().body, 'Try this ending')
        self.assertEqual(self.post(action='comment', user=self.commenter, body='', recording=upload('bad.wav', b'bad')).status_code, 409)
        self.assertEqual(self.song.comments.count(), 1)
        self.assertEqual(Recording.objects.count(), 1)
        self.assertEqual(self.post(action='comment', user=self.pending, body='Not approved', recording=upload()).status_code, 403)

    def test_audio_upload_requires_contributor_agreement(self):
        Membership.objects.filter(user=self.author).update(agreement_version='')
        self.assertEqual(self.post().status_code, 409)
        self.assertFalse(Recording.objects.exists())

    def test_recording_only_tune_can_be_approved(self):
        self.song.parts.filter(kind='tune').update(content='', license_code='')
        self.assertEqual(self.post().status_code, 200)
        self.song.refresh_from_db()
        act(self.reviewer, self.song.pk, 'approve', {'scope':'tune','song_revision':str(self.song.revision)})
        self.assertEqual(self.song.approvals.count(), 1)

    def test_ranges_suffix_head_cache_and_missing_recording(self):
        self.post()
        item = Recording.objects.get()
        url = item.get_absolute_url()
        content = wave_bytes()
        for range_header, expected in [('bytes=0-43',content[:44]), ('bytes=44-',content[44:]), ('bytes=-12',content[-12:])]:
            with self.subTest(range_header=range_header):
                response = self.client.get(url, HTTP_RANGE=range_header)
                self.assertEqual(response.status_code, 206)
                self.assertEqual(b''.join(response.streaming_content), expected)
                self.assertEqual(int(response['Content-Length']), len(expected))
        for invalid in ('bytes=999999-','bytes=44-12','bytes=-0','bytes=','bytes=0-1,4-5'):
            self.assertEqual(self.client.get(url, HTTP_RANGE=invalid).status_code, 416)
        head = self.client.head(url)
        self.assertEqual(int(head['Content-Length']), len(content))
        self.assertEqual(head.content, b'')
        self.assertEqual(self.client.get(url,HTTP_IF_NONE_MATCH=head['ETag']).status_code,304)
        response = self.client.get(url, HTTP_RANGE='bytes=0-1', HTTP_IF_RANGE='old-etag')
        self.assertEqual(response.status_code,200)
        response.close()
        self.assertEqual(self.client.get(f'/recordings/{uuid.uuid4()}/').status_code,404)
        item.file.storage.delete(item.file.name)
        self.assertEqual(self.client.get(url).status_code,404)

    def test_recorded_comment_on_lyrics_survives_unrelated_tune_edit(self):
        self.post()
        response = self.post(action='comment', user=self.commenter, scope='lyrics',
                             song_revision='1', part_revision='1', body='My sung suggestion', recording=upload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.song.comments.get().scope, 'lyrics')
        self.assertEqual(self.post(action='comment',user=self.commenter,part_revision='1',recording=upload()).status_code,409)

    def test_removing_last_tune_recording_cannot_publish_an_empty_tune(self):
        self.song.parts.filter(kind='tune').update(content='')
        self.post()
        self.song.stage='frozen'
        self.song.save()
        self.assertEqual(self.post(action='remove_recording',user=self.reviewer).status_code,200)
        self.song.refresh_from_db()
        for number in range(5):
            reviewer=self.member(f'finalreviewer{number}','reviewer')
            act(reviewer,self.song.pk,'approve',{'scope':'publish','song_revision':str(self.song.revision)})
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            act(self.reviewer,self.song.pk,'publish',{'song_revision':str(self.song.revision)})
        self.song.refresh_from_db()
        self.assertEqual(self.song.stage,'frozen')
