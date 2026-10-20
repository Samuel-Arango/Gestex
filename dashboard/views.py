from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required


@login_required
@staff_member_required
def dashboard_home(request):
    context = {
        'title': 'Dashboard',
    }
    return render(request, 'dashboard/home.html', context)
