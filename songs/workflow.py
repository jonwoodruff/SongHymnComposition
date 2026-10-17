from datetime import timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Song, Approval, Revision, EditLock, Membership

def role(user):
    if not user.is_authenticated or not user.is_active: return 'visitor'
    return Membership.objects.filter(user=user).values_list('role',flat=True).first() or 'pending'

def require(condition, message):
    if not condition: raise ValidationError(message)

def can_edit(user, song):
    r = role(user)
    return song.stage != 'published' and (r == 'reviewer' or (song.stage == 'draft' and song.author_id == user.pk and r == 'contributor'))

def count(song, scope, revision, exclude_author=False):
    qs = song.approvals.filter(scope=scope, revision=revision, user__is_active=True, user__membership__role='reviewer')
    if exclude_author: qs = qs.exclude(user_id=song.author_id)
    return qs.count()

@transaction.atomic
def act(user, song_id, action, data):
    song = Song.objects.select_for_update().get(pk=song_id)
    r = role(user)
    if r not in ('commenter', 'contributor', 'reviewer'): raise PermissionDenied
    require(str(song.revision) == data.get('song_revision'), 'This song changed since you opened it. Reload before continuing.')
    if action in ('lock', 'save'):
        if not can_edit(user, song): raise PermissionDenied
        part = song.parts.get(kind=data.get('scope'))
        lock = EditLock.objects.filter(part=part).first()
        if action == 'lock':
            require(not lock or lock.expires <= timezone.now() or lock.user_id == user.pk, 'Someone else holds this editing lock.')
            EditLock.objects.update_or_create(part=part, defaults={'user':user, 'expires':timezone.now()+timedelta(minutes=15)})
            return
        require(not lock or lock.expires <= timezone.now() or lock.user_id == user.pk,
                'Someone else holds this editing lock. Your text has been kept below; try again when they finish.')
        require(str(part.revision) == data.get('revision'), 'This section changed. Reload before saving.')
        content = data.get('content','').strip()
        require(bool(content), 'Please provide content.')
        part.content = content
        part.revision += 1
        part.save()
        Revision.objects.create(part=part, number=part.revision, content=content, editor=user)
        song.revision += 1
        song.author_signed = False
        song.save()
        if lock:
            lock.delete()
    elif action == 'comment':
        scope = data.get('scope')
        require(scope in ('concept','lyrics','tune','review'), 'Choose a valid discussion area.')
        body = data.get('body','').strip()
        require(bool(body), 'Please write a comment.')
        rev = song.revision if scope == 'review' else song.parts.get(kind=scope).revision
        song.comments.create(user=user, scope=scope, revision=rev, anchor=data.get('anchor','')[:500], body=body)
    elif action == 'sign':
        require(song.stage == 'draft' and song.author_id == user.pk, 'Only the author can sign off a draft.')
        song.author_signed = True
        song.save()
    elif action == 'approve':
        if r != 'reviewer': raise PermissionDenied
        scope = data.get('scope')
        if song.stage == 'draft':
            require(scope in ('concept','lyrics','tune'), 'Choose a workstream.')
            part = song.parts.get(kind=scope)
            require(bool(part.content.strip()), 'An empty section cannot be approved.')
            rev = part.revision
        else:
            require(song.stage == 'frozen' and scope == 'publish' and user.pk != song.author_id, 'Publication requires independent experienced reviewers.')
            rev = song.revision
        Approval.objects.get_or_create(song=song,user=user,scope=scope,revision=rev)
    elif action == 'freeze':
        require(user.pk == song.author_id or r == 'reviewer', 'Only the author or an experienced reviewer can freeze a draft.')
        require(song.stage == 'draft' and song.author_signed, 'The author must sign off first.')
        require(all(p.content.strip() and count(song,p.kind,p.revision)>=2 for p in song.parts.all()) and song.parts.count()==3, 'Each workstream needs two experienced approvals.')
        song.stage='frozen'
        song.save()
        EditLock.objects.filter(part__song=song).delete()
    elif action == 'publish':
        if r != 'reviewer': raise PermissionDenied
        require(song.stage=='frozen' and count(song,'publish',song.revision,True)>=5, 'Five independent experienced approvals are required for this revision.')
        song.stage='published'
        song.save()
    elif action == 'request_rework':
        require(song.stage=='frozen' and user.pk==song.author_id, 'Only the author can request rework during frozen review.')
        song.rework_requested=True
        song.save()
    elif action == 'return':
        if r != 'reviewer': raise PermissionDenied
        require(song.stage=='frozen' and song.rework_requested, 'The author must request rework first.')
        Approval.objects.get_or_create(song=song,user=user,scope='return',revision=song.revision)
        if count(song,'return',song.revision)>=2:
            song.stage='draft'
            song.revision+=1
            song.author_signed=False
            song.rework_requested=False
            song.approvals.all().delete()
            song.save()
    else: raise ValidationError('Unknown action.')
