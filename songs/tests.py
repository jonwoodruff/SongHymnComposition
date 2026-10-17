from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from datetime import timedelta
from .models import Song, Part, Membership, Approval, EditLock
from .workflow import act, count
from .policy import AGREEMENT_VERSION

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class WorkflowTests(TestCase):
    def setUp(self):
        self.author=self.member('author','contributor')
        self.commenter=self.member('commenter','commenter')
        self.reviewers=[self.member(f'reviewer{i}','reviewer') for i in range(6)]
        self.song=Song.objects.create(title='A shared song',author=self.author)
        for kind in ('concept','lyrics','tune'): Part.objects.create(song=self.song,kind=kind,content='First version', license_code='CC-BY-4.0')
    def member(self,name,role):
        user=User.objects.create_user(name,password='test-pass-2026')
        Membership.objects.create(user=user,role=role,interests='compose',testimony='Private testimony',experience='Singing', agreement_version=AGREEMENT_VERSION, agreement_accepted_at=timezone.now())
        return user
    def do(self,user,action,**data):
        self.song.refresh_from_db()
        return act(user,self.song.pk,action,{'song_revision':str(self.song.revision),'stage':self.song.stage,**data})
    def freeze(self):
        for kind in ('concept','lyrics','tune'):
            for reviewer in self.reviewers[:2]: self.do(reviewer,'approve',scope=kind)
        self.do(self.author,'sign')
        self.do(self.author,'freeze')
        self.song.refresh_from_db()
    def test_parallel_gates_and_author_signoff(self):
        with self.assertRaises(ValidationError): self.do(self.author,'freeze')
        for kind in ('concept','lyrics','tune'):
            for reviewer in self.reviewers[:2]: self.do(reviewer,'approve',scope=kind)
        with self.assertRaises(ValidationError): self.do(self.reviewers[0],'freeze')
        self.do(self.author,'sign');self.do(self.author,'freeze')
        self.song.refresh_from_db();self.assertEqual(self.song.stage,'frozen')
    def test_five_distinct_independent_approvals(self):
        self.freeze()
        Membership.objects.filter(user=self.author).update(role='reviewer')
        with self.assertRaises(ValidationError): self.do(self.author,'approve',scope='publish')
        for _ in range(5): self.do(self.reviewers[0],'approve',scope='publish')
        with self.assertRaises(ValidationError): self.do(self.reviewers[0],'publish')
        for reviewer in self.reviewers[1:5]:self.do(reviewer,'approve',scope='publish')
        self.do(self.reviewers[0],'publish');self.song.refresh_from_db()
        self.assertEqual(self.song.stage,'published')
        with self.assertRaises(PermissionDenied):self.do(self.reviewers[0],'lock',scope='lyrics')
    def test_permissions_and_locks(self):
        outsider=self.member('other','contributor')
        for user in (self.commenter,outsider):
            with self.assertRaises(PermissionDenied):self.do(user,'lock',scope='lyrics')
        self.do(self.author,'lock',scope='lyrics')
        with self.assertRaises(ValidationError):self.do(self.reviewers[0],'lock',scope='lyrics')
        self.do(self.author,'save',scope='lyrics',revision='1',content='Changed')
        self.assertEqual(self.song.parts.get(kind='lyrics').revision,2)
        self.assertEqual(self.song.parts.get(kind='lyrics').history.count(),1)
    def test_expired_lock_and_stale_revision(self):
        self.do(self.author,'lock',scope='lyrics')
        EditLock.objects.update(expires=timezone.now()-timedelta(seconds=1))
        self.do(self.reviewers[0],'lock',scope='lyrics')
        with self.assertRaises(ValidationError):self.do(self.author,'save',scope='lyrics',revision='1',content='Changed')
        EditLock.objects.all().delete()
        self.do(self.author,'lock',scope='lyrics')
        with self.assertRaises(ValidationError):self.do(self.author,'save',scope='lyrics',revision='0',content='Changed')
    def test_edit_invalidates_only_changed_stream_and_author_signoff(self):
        for kind in ('concept','lyrics'):
            self.do(self.reviewers[0],'approve',scope=kind)
        self.do(self.author,'sign');self.do(self.author,'lock',scope='lyrics')
        self.do(self.author,'save',scope='lyrics',revision='1',content='Changed lyrics')
        self.song.refresh_from_db()
        self.assertFalse(self.song.author_signed)
        self.assertEqual(count(self.song,'lyrics',2),0)
        self.assertEqual(count(self.song,'concept',1),1)
        with self.assertRaises(ValidationError):act(self.reviewers[0],self.song.pk,'approve',{'scope':'lyrics','song_revision':'1'})
    def test_frozen_edits_invalidate_publication_votes(self):
        self.freeze();self.do(self.reviewers[0],'approve',scope='publish')
        with self.assertRaises(PermissionDenied):self.do(self.author,'lock',scope='lyrics')
        self.do(self.reviewers[0],'lock',scope='lyrics')
        self.do(self.reviewers[0],'save',scope='lyrics',revision='1',content='Editorial change')
        self.song.refresh_from_db();self.assertEqual(count(self.song,'publish',self.song.revision,True),0)
    def test_return_requires_author_and_two_distinct_reviewers(self):
        self.freeze()
        with self.assertRaises(ValidationError):self.do(self.reviewers[0],'return')
        self.do(self.author,'request_rework')
        for _ in range(2):self.do(self.reviewers[0],'return')
        self.song.refresh_from_db();self.assertEqual(self.song.stage,'frozen')
        self.do(self.reviewers[1],'return')
        self.song.refresh_from_db();self.assertEqual(self.song.stage,'draft')
        self.assertFalse(self.song.author_signed);self.assertFalse(self.song.approvals.exists())
    def test_pending_members_cannot_comment_and_comments_keep_revision(self):
        pending=self.member('pending','pending')
        with self.assertRaises(PermissionDenied):self.do(pending,'comment',scope='lyrics',body='hello')
        self.do(self.commenter,'comment',scope='lyrics',body='Suggestion',anchor='First')
        self.do(self.author,'lock',scope='lyrics');self.do(self.author,'save',scope='lyrics',revision='1',content='Revised')
        self.assertEqual(self.song.comments.get().revision,1)
    def test_public_pages_and_privacy(self):
        for url in ('/',f'/songs/{self.song.pk}/','/join/','/accounts/login/'):
            response=self.client.get(url);self.assertEqual(response.status_code,200)
            self.assertNotContains(response,'Private testimony')
        self.client.force_login(self.author)
        self.assertEqual(self.client.get(f'/songs/{self.song.pk}/').status_code,200)
    def test_csrf_protected(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.author)
        response=client.post(f'/songs/{self.song.pk}/',{'action':'sign','song_revision':'1'})
        self.assertEqual(response.status_code,403)
    def test_membership_request_does_not_grant_requested_role(self):
        response=self.client.post('/join/',{'username':'applicant','email':'test@example.com','interests':['review'],'testimony':'My testimony','experience':'My experience','password1':'Long-test-password-2026','password2':'Long-test-password-2026','fellowship':'on','licensing':'on'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(Membership.objects.get(user__username='applicant').role,'pending')
    def test_demoted_reviewers_no_longer_count(self):
        self.do(self.reviewers[0],'approve',scope='concept')
        Membership.objects.filter(user=self.reviewers[0]).update(role='commenter')
        self.assertEqual(count(self.song,'concept',1),0)

    def test_save_concept_and_lyrics_without_manual_lock(self):
        self.client.force_login(self.author)
        for kind in ('concept', 'lyrics'):
            self.song.refresh_from_db()
            content = f"My {kind}\nA second line & a <phrase>"
            response = self.client.post(f'/songs/{self.song.pk}/', {
                'action': 'save', 'scope': kind, 'revision': '1',
                'song_revision': str(self.song.revision), 'content': content,
            }, follow=True)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.song.parts.get(kind=kind).content, content)
            self.assertContains(response, 'Saved.')
            self.assertContains(response, f'My {kind}')

    def test_rejected_save_keeps_text_and_editor_open(self):
        self.client.force_login(self.author)
        self.do(self.reviewers[0], 'lock', scope='lyrics')
        response = self.client.post(f'/songs/{self.song.pk}/', {
            'action': 'save', 'scope': 'lyrics', 'revision': '1',
            'song_revision': '1', 'content': 'Do not lose this <draft>',
        })
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, 'Do not lose this &lt;draft&gt;', status_code=409)
        self.assertContains(response, 'class="section-editor" open', status_code=409)
        self.assertEqual(self.song.parts.get(kind='lyrics').content, 'First version')

    def test_stale_save_keeps_original_revision_to_prevent_overwrite(self):
        self.client.force_login(self.author)
        self.do(self.reviewers[0], 'save', scope='lyrics', revision='1', content='Newer lyrics')
        response = self.client.post(f'/songs/{self.song.pk}/', {
            'action': 'save', 'scope': 'lyrics', 'revision': '1',
            'song_revision': '1', 'content': 'My older draft',
        })
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, 'My older draft', status_code=409)
        lyrics = next(p for p in response.context['parts'] if p.kind == 'lyrics')
        self.assertEqual(lyrics.edit_revision, '1')
        self.assertEqual(lyrics.revision, 2)
        self.assertEqual(lyrics.content, 'Newer lyrics')

    def test_lock_can_be_requested_without_page_navigation(self):
        self.client.force_login(self.author)
        payload = {'action': 'lock', 'scope': 'lyrics', 'song_revision': '1', 'stage':'draft'}
        response = self.client.post(f'/songs/{self.song.pk}/', payload, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('message', response.json())
        self.assertEqual(EditLock.objects.get(part__kind='lyrics').user, self.author)
        self.client.force_login(self.reviewers[0])
        response = self.client.post(f'/songs/{self.song.pk}/', payload, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 409)
        self.assertIn('error', response.json())

    def test_expired_lock_can_be_saved_if_revision_is_current(self):
        self.do(self.author, 'lock', scope='lyrics')
        EditLock.objects.update(expires=timezone.now()-timedelta(seconds=1))
        self.do(self.author, 'save', scope='lyrics', revision='1', content='Saved after expiry')
        self.assertEqual(self.song.parts.get(kind='lyrics').content, 'Saved after expiry')

    def autosave(self, user, kind, content, revision='1', stage='draft'):
        self.client.force_login(user)
        return self.client.post(f'/songs/{self.song.pk}/', {
            'action':'autosave', 'scope':kind, 'content':content,
            'revision':revision, 'stage':stage, 'song_revision':'1',
        }, HTTP_ACCEPT='application/json')

    def test_autosaves_to_different_sections_do_not_conflict(self):
        first=self.autosave(self.author, 'concept', 'A new concept')
        second=self.autosave(self.reviewers[0], 'lyrics', 'New lyrics from the same starting song version')
        self.assertEqual(first.status_code,200)
        self.assertEqual(second.status_code,200)
        self.assertEqual(self.song.parts.get(kind='concept').content,'A new concept')
        self.assertEqual(self.song.parts.get(kind='lyrics').revision,2)

    def test_autosave_rejects_stale_section_without_overwrite(self):
        self.assertEqual(self.autosave(self.author,'lyrics','First saved change').status_code,200)
        stale=self.autosave(self.author,'lyrics','Stale competing text')
        self.assertEqual(stale.status_code,409)
        self.assertEqual(self.song.parts.get(kind='lyrics').content,'First saved change')

    def test_autosave_does_not_invalidate_approvals_for_unchanged_content(self):
        self.do(self.reviewers[0],'approve',scope='lyrics')
        self.do(self.author,'sign')
        response=self.autosave(self.author,'lyrics','First version')
        self.assertEqual(response.status_code,200)
        self.song.refresh_from_db()
        self.assertTrue(self.song.author_signed)
        self.assertEqual(self.song.revision,1)
        self.assertEqual(count(self.song,'lyrics',1),1)

    def test_autosave_respects_other_editor_and_stage(self):
        self.do(self.reviewers[0],'lock',scope='lyrics')
        self.assertEqual(self.autosave(self.author,'lyrics','Competing text').status_code,409)
        self.freeze()
        self.assertEqual(self.autosave(self.reviewers[0],'concept','Wrong stage').status_code,409)
        self.assertEqual(self.autosave(self.author,'concept','Author cannot edit frozen',stage='frozen').status_code,403)
        self.assertEqual(self.autosave(self.reviewers[0],'concept','Editorial change',stage='frozen').status_code,200)

    def test_presence_release_and_public_live_state(self):
        self.do(self.author,'lock',scope='lyrics')
        self.client.logout()
        state=self.client.get(f'/songs/{self.song.pk}/state/').json()
        lyrics=next(p for p in state['parts'] if p['kind']=='lyrics')
        self.assertEqual(lyrics['editor'],self.author.username)
        self.assertFalse(lyrics['editing_here'])
        self.assertNotIn('testimony',str(state))
        self.do(self.reviewers[0],'release',scope='lyrics')
        self.assertTrue(EditLock.objects.filter(part__kind='lyrics').exists())
        self.do(self.author,'release',scope='lyrics')
        self.assertFalse(EditLock.objects.filter(part__kind='lyrics').exists())

    def test_live_comments_are_escaped_and_revision_checked(self):
        self.do(self.commenter,'comment',scope='lyrics',body='<script>alert(1)</script>',anchor='First')
        state=self.client.get(f'/songs/{self.song.pk}/state/').json()
        self.assertIn('&lt;script&gt;',state['comments_html'])
        self.assertNotIn('<script>',state['comments_html'])
        self.assertEqual(state['annotations'][0]['anchor'],'First')
        self.do(self.author,'save',scope='lyrics',revision='1',content='New words')
        with self.assertRaises(ValidationError):
            self.do(self.commenter,'comment',scope='lyrics',body='Old selection',part_revision='1')
        self.assertEqual(self.song.comments.count(),1)

    def test_signup_requires_both_agreements(self):
        payload={'username':'noagreement','email':'a@example.com','interests':['compose'],
            'testimony':'Testimony','experience':'Singing','password1':'Long-test-password-2026','password2':'Long-test-password-2026'}
        response=self.client.post('/join/',payload)
        self.assertEqual(response.status_code,200)
        self.assertFalse(User.objects.filter(username='noagreement').exists())
        payload.update(fellowship='on',licensing='on')
        self.client.post('/join/',payload)
        member=Membership.objects.get(user__username='noagreement')
        self.assertEqual(member.agreement_version,AGREEMENT_VERSION)
        self.assertIsNotNone(member.agreement_accepted_at)
        self.assertEqual(member.role,'pending')

    def test_existing_members_must_accept_before_new_content(self):
        Membership.objects.filter(user=self.author).update(agreement_version='',agreement_accepted_at=None)
        self.assertEqual(self.autosave(self.author,'lyrics','Not yet consented').status_code,409)
        response=self.client.post('/agreement/',{'fellowship':'on','licensing':'on'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.autosave(self.author,'lyrics','Consented change').status_code,200)
        part=self.song.parts.get(kind='lyrics')
        self.assertEqual(part.license_code,'CC-BY-4.0')
        self.assertEqual(part.history.get().license_code,'CC-BY-4.0')

    def test_unlicensed_legacy_content_is_not_silently_published(self):
        self.song.parts.filter(kind='lyrics').update(license_code='')
        self.freeze()
        for reviewer in self.reviewers[:5]:self.do(reviewer,'approve',scope='publish')
        with self.assertRaises(ValidationError):self.do(self.reviewers[0],'publish')
        self.song.refresh_from_db()
        self.assertEqual(self.song.stage,'frozen')

    def test_published_edition_records_licence_without_changing_earlier_revisions(self):
        self.freeze()
        for reviewer in self.reviewers[:5]:self.do(reviewer,'approve',scope='publish')
        self.do(self.reviewers[0],'publish')
        self.song.refresh_from_db()
        self.assertEqual(self.song.publication_license_code,'CC-BY-ND-4.0')
        self.assertEqual(set(self.song.parts.values_list('license_code',flat=True)),{'CC-BY-4.0'})

    def test_autosave_normalizes_browser_form_newlines(self):
        response=self.autosave(self.author,'concept','First line\r\nSecond line')
        self.assertEqual(response.status_code,200)
        part=self.song.parts.get(kind='concept')
        self.assertEqual(part.content,'First line\nSecond line')
        next_save=self.autosave(self.author,'concept','First line\r\nSecond line',revision='2')
        self.assertEqual(next_save.status_code,200)
        part.refresh_from_db()
        self.assertEqual(part.revision,2)

    def test_legacy_section_needs_explicit_author_confirmation(self):
        part=self.song.parts.get(kind='lyrics');part.license_code='';part.save()
        with self.assertRaises(ValidationError):self.do(self.author,'license',scope='lyrics')
        with self.assertRaises(ValidationError):self.do(self.reviewers[0],'license',scope='lyrics',rights_confirmed='on')
        self.do(self.author,'license',scope='lyrics',rights_confirmed='on')
        part.refresh_from_db()
        self.assertEqual(part.content,'First version')
        self.assertEqual(part.license_code,'CC-BY-4.0')
        self.assertEqual(part.revision,2)
