from django.shortcuts import get_object_or_404
from forms import FeedbackForm, RegistrationForm
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponseRedirect
from django.shortcuts import render
from helpdesk.models import DocumentationApp, FAQ
from django.contrib.auth.views import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from helpdesk.github import latest_release, update_issue, get_issue, queue_repo, get_issue_status
from helpdesk.models import Ticket, Queue, FollowUp
from tasks.models import Task
from django.conf import settings
from django.db.models import Count, Sum
import os
from project.models import LoggedUser
from helpdesk.forms import TicketForm, PublicTicketForm
from datetime import datetime as timezone
from helpdesk.views.staff import file_attachment
from helpdesk.views.staff import data_query_pagination
from helpdesk.slack import post_slack,post_tola_slack

from django.contrib.sessions.models import Session
try:
    from django.utils import timezone
except ImportError:
    from datetime import datetime as timezone

from helpdesk.views.staff import form_data, user_tickets

def splash(request):
    if request.user.is_authenticated():

        return home(request)
        
    return render(request, "splash.html")

@login_required
def user (request):
    email = request.GET.get('email')
    username = request.GET.get('username')
    user = User.objects.filter(email=email).values('username').all()[:1]

    try:
        user_id = User.objects.get(username=user).id
    except Exception, e:
        user_id = 0

    all_tickets = {}
    total_tickets = 0
    all_tasks = {}
    tickets_created = {}
    total_tickets_created = 0
    tickets_assigned = {}
    total_tickets_assigned = 0
    tickets_closed_resolved = {}
    total_tickets_closed_resolved = 0
    tasks_created = {}
    tasks_assigned = {}
    total_tasks = {}
    total_tasks_created = 0
    total_tasks_assigned = 0
    tasks_completed = {}
    total_tasks_completed = 0

    #tickets
    if user_id:
        try:
            tickets = get_tickets_by_user(email)
            all_tickets = (tickets).values('status').annotate(total=Count('status')).order_by('total')
            total_tickets = len(tickets)

            #created by logged_in user
            tickets_created = (tickets).select_related('queue').exclude(status__in=([3,4,5])).order_by('-created')[:5]
            total_tickets_created = len(tickets_created)

            #assigned to the user
            tickets_assigned = Ticket.objects.select_related('queue').filter(
                    assigned_to=user_id,
                 ).exclude(
                    status__in=([3,4,5]),
                ).order_by('-created')[:5]

            total_tickets_assigned=len(tickets_assigned)

            #closed and resolved by user
            tickets_closed_resolved = Ticket.objects.select_related('queue').filter(
                assigned_to=user_id,
                    status__in=[3,4],
                ).order_by('-created')[:5]

            total_tickets_closed_resolved = len(tickets_closed_resolved)

            #tasks
            tasks = get_tasks_by_user(email)
            all_tasks = (tasks).values('status').annotate(total=Count('status')).order_by('total')
            total_tasks= len(tasks)

            #tasks created by user
            tasks_created = (tasks).exclude(status__in=([3,4])).order_by('created_date')[:5]
            total_tasks_created = len(tasks_created)

            #tasks assigned to the user
            tasks_assigned = Task.objects.filter(assigned_to_id=user_id).exclude(status__in=([3,4])).order_by('created_date')[:5]
            total_tasks_assigned = len(tasks_assigned)

            #tasks completed by the user
            tasks_completed = (tasks).filter(status__in='3').order_by('created_date')[:5]
            total_tasks_completed = len (tasks_completed)

        except Exception, e:
            pass  



    logged_users = logged_in_users(request)

    return render(request, "user.html", {'all_tickets': all_tickets,'total_tickets': total_tickets, 'all_tasks': all_tasks, \
                                        'logged_users': logged_users, 'username': username,'tickets_created': tickets_created, 'total_tickets_created':total_tickets_created, \
                                        'tickets_assigned': tickets_assigned, 'total_tickets_assigned': total_tickets_assigned, 'tickets_closed_resolved': tickets_closed_resolved, \
                                        'total_tickets_closed_resolved': total_tickets_closed_resolved,'tasks_created': tasks_created, 'tasks_assigned': tasks_assigned, \
                                        'total_tasks': total_tasks, 'total_tasks_created': total_tasks_created,'total_tasks_assigned': total_tasks_assigned, 'tasks_completed': tasks_completed,\
                                         'total_tasks_completed': total_tasks_completed})

def home(request):

    #Ping Tola servers
    activity_up = os.system("ping -c 1 " + "http://tola-activity.mercycorps.org")
    data_up = os.system("ping -c 1 " + "http://tola-tables.mercycorps.org")

    #GitHub releases for status
    tola_repo = settings.GITHUB_REPO_1
    tola_activity_repo = settings.GITHUB_REPO_2

    tola = latest_release(tola_repo)
    if tola:
        tola_url = tola['html_url']
        tola_number = tola['tag_name']
    else:
        tola_url = None
        tola_number = None

    tola_activity = latest_release(tola_activity_repo)
    if tola_activity:
        tola_activity_url = tola_activity['html_url']
        tola_activity_number = tola_activity['tag_name']
    else:
        tola_activity_url = None
        tola_activity_number = None

    tickets = Ticket.objects.all().values('status').annotate(total=Count('status')).order_by('total')

    recent_tickets = Ticket.objects.all().exclude(status__in='4').order_by('-created')[:5]
    votes_tickets = Ticket.objects.all().exclude(status__in='4').filter(type=2).order_by('-votes')[:5]
    recent_tasks = Task.objects.all().order_by('-created_date')[:5]
    num_tickets = len(Ticket.objects.filter(status__in=[1,2,3]))
    num_tasks = len(Task.objects.all())

    closed_resolved = 0
    assigned_to_me = 0
    created_by_me = 0
    closed = []
    tome = []
    byme = []
    tasks_created = []
    total_tasks_created = 0
    tasks_assigned = []
    total_tasks_assigned = 0
    tasks_completed = []
    total_tasks_completed = 0
    if (request.user.is_authenticated()):
        #tickets
        # open & reopened tickets
        closedresolved = Ticket.objects.select_related('queue').filter(
            assigned_to=request.user,
            status__in=[Ticket.CLOSED_STATUS, Ticket.RESOLVED_STATUS],
        )
        closed=(closedresolved).order_by('-created')[:5]
        closed_resolved = len(closedresolved)

        # Tickets assigned to current user
        assigned_tome = Ticket.objects.select_related('queue').filter(
            assigned_to=request.user,
         ).exclude(
            status__in=[Ticket.CLOSED_STATUS, Ticket.RESOLVED_STATUS],
        )
        tome=(assigned_tome).order_by('-created')[:5]
        assigned_to_me=len(assigned_tome)


        # Tickets created by current user
        created_byme = Ticket.objects.select_related('queue').filter(
               submitter_email=request.user.email,
            ).exclude(
               status__in=[Ticket.CLOSED_STATUS, Ticket.RESOLVED_STATUS],
           )
        byme=(created_byme).order_by('-created')[:5]

        created_by_me = len(created_byme)

        #Tasks
        tasks = Task.objects.filter(submitter_email=request.user.email)
        all_tasks = (tasks).values('status').annotate(total=Count('status')).order_by('total')

        #tasks created by user
        tasks_created = (tasks).exclude(status__in=([3,4])).order_by('created_date')[:5]
        total_tasks_created = len(tasks_created)

        #tasks assigned to the user
        tasks_assigned = Task.objects.filter(assigned_to_id=request.user).exclude(status__in=([3,4])).order_by('created_date')[:5]
        total_tasks_assigned = len(tasks_assigned)

        #tasks completed by the user
        tasks_completed = (tasks).filter(status__in='3').order_by('created_date')[:5]
        total_tasks_completed = len (tasks_completed)

#----Data From Tola Tools APIs----####
    #get_TolaActivity_data() 
    tolaActivityData = get_TolaActivity_data()

    tolaTablesData = {}
    if request.user.is_authenticated():

        tolaTablesData = get_TolaTables_data(request)

    #create ticket modal
    assignable_users = User.objects.filter(is_active=True).order_by(User.USERNAME_FIELD)
    initial_data = {}
    try:
        if request.user.is_authenticated and request.user.email:
            initial_data['submitter_email'] = request.user.email

    except Exception, e:
        pass
    form = form_data(request)

    users = get_current_users()

    return render(request, 'home.html', {'home_tab': 'active', 'tola_url': tola_url,'tola_number': tola_number, \
                                         'tola_activity_url': tola_activity_url, 'tola_activity_number': tola_activity_number, \
                                         'activity_up': activity_up, 'data_up': data_up, 'tickets': tickets, \
                                         'recent_tickets': recent_tickets,'votes_tickets': votes_tickets, 'num_tickets': num_tickets, 'recent_tasks': recent_tasks, \
                                         'closed_resolved': closed_resolved,'assigned_to_me':assigned_to_me,'created_by_me':created_by_me,\
                                         'closed':closed,'tome':tome,'byme':byme, 'tasks_created': tasks_created, 'tasks_assigned': tasks_assigned, \
                                          'num_tasks': num_tasks, 'total_tasks_created': total_tasks_created, \
                                        'total_tasks_assigned': total_tasks_assigned, 'tasks_completed': tasks_completed, 'total_tasks_completed': total_tasks_completed, 
                                        'tolaActivityData': tolaActivityData, 'tolaTablesData':tolaTablesData, \
                                         'logged_users':users, 'form':form, 'helper':form.helper})


def contact(request):
    """
    Feedback form
    """
    form = FeedbackForm(initial={'submitter': request.user})

    if request.method == 'POST':
        form = FeedbackForm(request.POST)  # A form bound to the POST data
        if form.is_valid():  # All validation rules pass
            form.save()
            messages.error(request, 'Thank you', fail_silently=False)
        else:
            messages.error(request, 'Invalid', fail_silently=False)
            print form.errors

    return render(request, "contact.html", {'form': form, 'helper': FeedbackForm.helper})


def faq(request):
    """
    Get FAQ and display them on template
    """

    getFAQ = FAQ.objects.all()

    return render(request, 'faq.html', {'getFAQ': getFAQ})


def documentation(request):
    """
    Get Documentation and display them on template
    """

    getDocumentation = DocumentationApp.objects.all()

    return render(request, 'documentation.html', {'getDocumentation': getDocumentation})


def register(request):
    """
    Register a new User profile using built in Django Users Model
    """
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect("/login")
    else:
        form = UserCreationForm()
    return render(request, "registration/register.html", {
        'form': form,
    })


def profile(request):
    """
    Update a User profile using built in Django Users Model if the user is logged in
    otherwise redirect them to registration version
    """
    if request.user.is_authenticated():
        obj = get_object_or_404(User, username=request.user)
        form = RegistrationForm(request.POST or None, instance=obj,initial={'username': request.user})

        if request.method == 'POST':
            if form.is_valid():
                form.save()
                messages.error(request, 'Your profile has been updated.', fail_silently=False)

        return render(request, "registration/profile.html", {
            'form': form, 'helper': RegistrationForm.helper
        })
    else:
        return HttpResponseRedirect("/accounts/register")


def logout_view(request):
    """
    Logout a user
    """
    logout(request)
    # Redirect to a success page.
    return HttpResponseRedirect("/home")


def permission_denied(request):
    """
    Something unauthorized happened
    """
    return render(request, '401.html')

###Tola Tools API Views
import requests

def get_TolaActivity_data():

    #TolaActivity Url
    url = 'http://activity.toladata.io/api/projectagreements/' 

    token = settings.TOLA_ACTIVITY_TOKEN

    header = {'Authorization': 'token %s' % token}

    try:
        response = requests.get(url, headers=header)

        # Consider any status other than 2xx an error
        if not response.status_code // 100 == 2:
            return {}

        json_obj = response.json()
        print json_obj
        return json_obj

    except requests.exceptions.RequestException as e:
        # A serious problem happened, like an SSLError or InvalidURL
        print e
        return {}

    except ValueError:

        return {}

def get_TolaTables_data(request):
    import json

    url = 'http://127.0.0.1:8200/api/tolatablesdata' #TolaActivity Url

    token = settings.TOLA_TABLES_TOKEN

    header = {'Authorization': 'token %s' % token}

    email = request.user.email

    payload = {'email': email}

    #print email
    try:
        response = requests.get(url, params = payload, headers=header)

        # Consider any status other than 2xx an error
        if not response.status_code // 100 == 2:
            return {}

        json_obj = response.json()

        return json_obj

    except requests.exceptions.RequestException as e:
        # A serious problem happened, like an SSLError or InvalidURL
        return {}

    except ValueError:

        return {}
#return users logged into TolaWork 
def logged_in_users(request):

    logged_users = {}
    username = request.user.username

    logged_users = LoggedUser.objects.all().exclude(username=username).order_by('username')

    return logged_users

#get tickets of a logged in user
def  get_tickets_by_user(email):

    tickets = Ticket.objects.filter(submitter_email= email)
    
    return tickets

#get tasks of a logged_in user
def  get_tasks_by_user(email):
    tasks = Task.objects.filter(submitter_email= email)

    return tasks

#GitHub Sync
@login_required
def githubSync(request):

    tickets = Ticket.objects.select_related('queue').exclude(
            status__in=[Ticket.RESOLVED_STATUS],
        )
    for ticket in tickets:
        # Sync 'Closed' status in github to 'Resolved' status in TW
        if ticket.github_issue_number:
            queue = queue_repo(ticket)
            response = get_issue_status(queue,ticket)

            if response == 200:
                print 'GitHubSync Success - #' + str(ticket.github_issue_number)

    return HttpResponseRedirect('/home')

#Get users with active sessions
def get_current_users():
    active_sessions = Session.objects.filter(expire_date__gte=timezone.now())
    user_id_list = []
    for session in active_sessions:
        data = session.get_decoded()
        user_id_list.append(data.get('_auth_user_id', None))

    # Query all logged in users based on id list
    logged_users = User.objects.filter(id__in=user_id_list)
    for user in logged_users:
        user.email = User.objects.get(username=user).email
    return logged_users



