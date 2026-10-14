from django.contrib import admin

from .models import SupportEvent, SupportResource


@admin.register(SupportResource)
class SupportResourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'phone', 'is_verified', 'verified_at', 'is_active', 'sort_order')
    list_filter = ('kind', 'is_verified', 'is_active', 'service_mode')
    list_editable = ('is_active', 'sort_order')
    search_fields = ('name', 'location', 'description')


@admin.register(SupportEvent)
class SupportEventAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'level', 'trigger', 'source')
    list_filter = ('level', 'trigger', 'source')
    date_hierarchy = 'created_at'

    # Events are an audit trail written only by the safety check.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
