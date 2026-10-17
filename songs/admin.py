from django.contrib import admin
from .models import Membership, Song, Part, Revision, Approval, Comment, EditLock
@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display=['user','interests','role']
    list_filter=['role']
    search_fields=['user__username','user__email']
    list_editable=['role']
# Workflow records are read-only: approvals and publication must use the normal gates.
class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False
for model in (Song, Part, Revision, Approval, Comment, EditLock): admin.site.register(model,ReadOnlyAdmin)
admin.site.site_header='Song & Hymn · Administration'
