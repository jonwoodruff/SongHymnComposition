from django.contrib import admin
from django.urls import path, include
from songs import views
from songs.recordings import recording
urlpatterns = [path('recordings/<uuid:pk>/', recording, name='recording'), path('admin/', admin.site.urls), path('accounts/', include('django.contrib.auth.urls')), path('', views.index, name='index'), path('join/', views.join, name='join'), path('agreement/', views.agreement, name='agreement'), path('licensing/', views.licensing, name='licensing'), path('songs/<int:pk>/state/', views.state, name='state'), path('new/', views.create, name='create'), path('songs/<int:pk>/', views.detail, name='detail')]
