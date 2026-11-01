"""
Test settings without django-outputs, as a project that uses no exporter has them.
"""
from invoicing.tests.test_settings import *  # noqa: F401,F403
from invoicing.tests.test_settings import INSTALLED_APPS

INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'outputs']
INVOICING_MANAGERS = {}
# Invoice.language holds 2 characters; Django's default LANGUAGES has longer codes ('zh-hans').
INVOICING_LANGUAGES = [('en', 'English'), ('sk', 'Slovak')]
