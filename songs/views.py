from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction, OperationalError
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.template.loader import render_to_string
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from .models import Song, Membership, Part, Revision
from .forms import JoinForm, SongForm, AgreementForm
from .policy import AGREEMENT_VERSION, FELLOWSHIP_TEXT, LICENSE_TEXT
from .workflow import role, can_edit, count, act

def index(request):
    songs=Song.objects.select_related('author').order_by('-updated')
    if request.GET.get('stage') in ('draft','frozen','published'): songs=songs.filter(stage=request.GET['stage'])
    return render(request,'songs/index.html',{'songs':songs,'can_create':role(request.user) in ('contributor','reviewer')})

def join(request):
    form=JoinForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            user=form.save()
            Membership.objects.create(user=user,interests=', '.join(form.cleaned_data['interests']),testimony=form.cleaned_data['testimony'],experience=form.cleaned_data['experience'], agreement_version=AGREEMENT_VERSION, agreement_accepted_at=timezone.now())
        messages.success(request,'Your request has been received. You can sign in now; contributions become available after administrator approval.')
        return redirect('login')
    return render(request,'songs/form.html',{'form':form,'heading':'Join the writing table','intro':'Tell us a little about yourself. An administrator will review your request before you can contribute.'})

@login_required
def create(request):
    if role(request.user) not in ('contributor','reviewer'): raise PermissionDenied
    if not has_agreement(request.user): return redirect('agreement')
    form=SongForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            song=form.save(commit=False)
            song.author=request.user
            song.save()
            for kind in ('concept','lyrics','tune'): Part.objects.create(song=song,kind=kind)
        return redirect('detail',pk=song.pk)
    return render(request,'songs/form.html',{'form':form,'heading':'Begin a new song','intro':'Start with a title. Concept, lyrics and melody can develop alongside each other.'})

@never_cache
def detail(request,pk):
    song=get_object_or_404(Song.objects.select_related('author'),pk=pk)
    failed_save = None
    if request.method=='POST':
        if not request.user.is_authenticated: return redirect('login')
        try: act(request.user,song.pk,request.POST.get('action'),request.POST,request.FILES)
        except PermissionDenied:
            if request.headers.get('Accept') == 'application/json':
                return JsonResponse({'error': 'You do not currently have permission to edit this section.'}, status=403)
            raise
        except OperationalError:
            if request.headers.get('Accept') == 'application/json':
                return JsonResponse({'error': 'The server is busy. Your changes are still here; retry in a moment.'}, status=503)
            raise
        except ValidationError as error:
            if request.headers.get('Accept') == 'application/json':
                return JsonResponse({'error': ' '.join(error.messages)}, status=409)
            messages.error(request,' '.join(error.messages))
            if request.POST.get('action') == 'save':
                failed_save = request.POST
            else:
                return redirect('detail',pk=pk)
        else:
            if request.headers.get('Accept') == 'application/json':
                return JsonResponse({'message': 'Saved' if request.POST.get('action') in ('save','autosave') else 'Ready to edit', **song_state(request, song.pk)})
            messages.success(request,'Saved.')
            return redirect('detail',pk=pk)
        song.refresh_from_db()
    parts=list(song.parts.select_related('recording').all().order_by('id'))
    for part in parts:
        part.approval_count=count(song,part.kind,part.revision)
        part.editor_content = part.content
        part.save_failed = bool(failed_save and failed_save.get('scope') == part.kind)
        if part.save_failed:
            part.editor_content = failed_save.get('content', '')
            # Keep the submitted revision, so retrying cannot overwrite an unseen edit.
            part.edit_revision = failed_save.get('revision', '')
        else:
            part.edit_revision = str(part.revision)
    return render(request,'songs/detail.html',{'song':song,'parts':parts,'can_edit':can_edit(request.user,song),'can_comment':role(request.user) in ('commenter','contributor','reviewer'),'reviewer':role(request.user)=='reviewer','is_author':request.user.pk==song.author_id,'publication_count':count(song,'publish',song.revision,True),'comments':song.comments.select_related('user','recording'), 'contributors': sorted({song.author.username, *Revision.objects.filter(part__song=song).values_list('editor__username', flat=True)}), 'failed_save':failed_save, 'needs_agreement':request.user.is_authenticated and not has_agreement(request.user)}, status=409 if failed_save else 200)


def has_agreement(user):
    return user.is_authenticated and Membership.objects.filter(user=user, agreement_version=AGREEMENT_VERSION, agreement_accepted_at__isnull=False).exists()

@login_required
def agreement(request):
    form = AgreementForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        membership = get_object_or_404(Membership, user=request.user)
        membership.agreement_version = AGREEMENT_VERSION
        membership.agreement_accepted_at = timezone.now()
        membership.save(update_fields=['agreement_version', 'agreement_accepted_at'])
        messages.success(request, 'Thank you. Your agreement has been recorded for future contributions.')
        return redirect('index')
    return render(request, 'songs/form.html', {'form':form, 'heading':'Writing in fellowship', 'intro':'Please read this provisional agreement before making new contributions. Existing material is not automatically relicensed.'})

def licensing(request):
    return render(request, 'songs/licensing.html', {'fellowship':FELLOWSHIP_TEXT, 'licensing_text':LICENSE_TEXT})

def song_state(request, pk):
    # A transaction gives each response a consistent set of section revisions.
    with transaction.atomic():
        song = get_object_or_404(Song, pk=pk)
        parts = []
        for part in song.parts.select_related('recording').all().order_by('id'):
            lock = getattr(part, 'editlock', None)
            active = lock and lock.expires > timezone.now()
            parts.append({'kind':part.kind, 'content':part.content.replace('\r\n','\n').replace('\r','\n'), 'revision':part.revision,
                'approvals':count(song,part.kind,part.revision), 'license':part.license_code,
                'recording': {'url':part.recording.get_absolute_url(), 'name':part.recording.original_name, 'type':part.recording.media_type} if part.recording_id else None,
                'editor':lock.user.username if active else None,
                'editing_here':bool(active and lock.user_id==request.user.pk)})
        comments = list(song.comments.select_related('user','recording'))
        return {'revision':song.revision, 'stage':song.stage, 'stage_label':song.get_stage_display(),
            'can_edit':can_edit(request.user,song), 'parts':parts,
            'contributors':sorted({song.author.username, *Revision.objects.filter(part__song=song).values_list('editor__username',flat=True)}),
            'comments_html':render_to_string('songs/comments.html', {'comments':comments}),
            'annotations':[{'id':c.pk,'scope':c.scope,'revision':c.revision,'anchor':c.anchor} for c in comments],
            'author_signed':song.author_signed,
            'publication_count':count(song,'publish',song.revision,True)}

@never_cache
def state(request, pk):
    if request.method != 'GET':
        return JsonResponse({'error':'GET required'},status=405)
    return JsonResponse(song_state(request, pk))
