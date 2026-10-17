from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from .models import Song, Membership, Part
from .forms import JoinForm, SongForm
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
            Membership.objects.create(user=user,interests=', '.join(form.cleaned_data['interests']),testimony=form.cleaned_data['testimony'],experience=form.cleaned_data['experience'])
        messages.success(request,'Your request has been received. You can sign in now; contributions become available after administrator approval.')
        return redirect('login')
    return render(request,'songs/form.html',{'form':form,'heading':'Join the writing table','intro':'Tell us a little about yourself. An administrator will review your request before you can contribute.'})

@login_required
def create(request):
    if role(request.user) not in ('contributor','reviewer'): raise PermissionDenied
    form=SongForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            song=form.save(commit=False)
            song.author=request.user
            song.save()
            for kind in ('concept','lyrics','tune'): Part.objects.create(song=song,kind=kind)
        return redirect('detail',pk=song.pk)
    return render(request,'songs/form.html',{'form':form,'heading':'Begin a new song','intro':'Start with a title. Concept, lyrics and melody can develop alongside each other.'})

def detail(request,pk):
    song=get_object_or_404(Song.objects.select_related('author'),pk=pk)
    if request.method=='POST':
        if not request.user.is_authenticated: return redirect('login')
        try: act(request.user,song.pk,request.POST.get('action'),request.POST)
        except ValidationError as error: messages.error(request,' '.join(error.messages))
        else: messages.success(request,'Saved.')
        return redirect('detail',pk=pk)
    parts=list(song.parts.all().order_by('id'))
    for part in parts:
        part.approval_count=count(song,part.kind,part.revision)
    return render(request,'songs/detail.html',{'song':song,'parts':parts,'can_edit':can_edit(request.user,song),'can_comment':role(request.user) in ('commenter','contributor','reviewer'),'reviewer':role(request.user)=='reviewer','is_author':request.user.pk==song.author_id,'publication_count':count(song,'publish',song.revision,True),'comments':song.comments.select_related('user')})
