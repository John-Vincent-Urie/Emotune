from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static
from api.views import admin_panel

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('api/users/', include('users.urls')),
    path('admin-panel/', admin_panel, name='admin_panel'),
    # The root is a convenience entry point only; admin_panel itself is what
    # enforces staff access, so an anonymous visitor lands on the login page.
    path('', RedirectView.as_view(pattern_name='admin_panel', permanent=False), name='root'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
