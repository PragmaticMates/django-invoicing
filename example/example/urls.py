from django.conf import settings
from django.conf.urls import patterns, include, url

# Uncomment the next two lines to enable the admin:
from django.contrib import admin


admin.autodiscover()

urlpatterns = patterns('',
    # Uncomment the admin/doc line below to enable admin documentation:
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    url(r'^admin/', include(admin.site.urls)),
)


if 'invoicing' in settings.INSTALLED_APPS:
    urlpatterns += patterns('',
        url(r'^invoicing/', include('invoicing.urls', app_name='invoicing', namespace='invoicing')),
    )
