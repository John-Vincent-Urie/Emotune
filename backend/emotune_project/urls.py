from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from api.views import admin_panel

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('api/users/', include('users.urls')),
    path('admin-panel/', admin_panel, name='admin_panel'),
    path('', admin_panel, name='root'),  # root also shows admin panel
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
