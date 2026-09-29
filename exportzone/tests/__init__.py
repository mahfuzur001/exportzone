"""Cross-app test suite.

Making ``tests`` a real package (this file) is what lets a bare
``python manage.py test`` discover these modules: without it the directory is an
unnamed namespace folder, unittest discovery skips it, and the command reports
"Found 0 test(s)" even though every test file is present.
"""
