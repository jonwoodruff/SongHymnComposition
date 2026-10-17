from django.contrib import admin
from django.urls import path, include
from songs import views
urlpatterns = [path('admin/', admin.site.urls), path('accounts/', include('django.contrib.auth.urls')), path('', views.index, name='index'), path('join/', views.join, name='join'), path('new/', views.create, name='create'), path('songs/<int:pk>/', views.detail, name='detail')]
