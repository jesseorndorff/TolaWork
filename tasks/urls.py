from django.conf.urls import *
from django.contrib import admin
from . import views

urlpatterns = patterns('tasks.views',

    url(r'^admin/', admin.site.urls),
    
    url(r'^tasks/$',
        'task_list',
        name='task_list'),

    url(r'^tasks/submit/$',
        'create_task',
        name='task_submit'),
    url(r'^tasks/(?P<task_id>[0-9]+)/$',
        'view_task',
        name='view_task'),
    url(r'^tasks/(?P<task_id>[0-9]+)/task_edit/$',
        'task_edit',
        name='task_edit'),
    url(r'^tasks/(?P<task_id>[0-9]+)/delete/$',
        'delete_task',
        name='delete_task'),

)
