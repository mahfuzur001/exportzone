"""Application package for the Export Zone storefront.

Django resolves the apps in INSTALLED_APPS as ``apps.<app>``, which needs this
directory to be an importable package. Without the marker file the directory
still works at runtime as an implicit namespace package, but a bare
``python manage.py test`` cannot walk into it and silently reports
"Found 0 test(s)" while every test file is present.
"""
