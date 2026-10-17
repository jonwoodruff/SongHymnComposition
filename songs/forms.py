from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Song
class JoinForm(UserCreationForm):
    email = forms.EmailField()
    interests = forms.MultipleChoiceField(choices=[('compose','Compose songs'),('comment','Comment on compositions'),('review','Contribute experienced reviews')], widget=forms.CheckboxSelectMultiple)
    testimony = forms.CharField(widget=forms.Textarea, help_text='A little about your testimony.')
    experience = forms.CharField(widget=forms.Textarea, help_text='Your experience of composing, singing, or appreciating songs and hymns.')
    class Meta:
        model=User
        fields=['username','email','interests','testimony','experience','password1','password2']
class SongForm(forms.ModelForm):
    class Meta:
        model=Song
        fields=['title']
