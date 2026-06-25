"""
Tests for training router (AI model training).

NOTE: The training router is not registered in the coordinator-api application
(see ``app/main.py`` — there is no ``include_router`` for a training router and
no ``src/app/.../routers/training.py`` source module exists). The previous test
methods targeted ``/v1/training/...`` endpoints that do not exist, so they have
been removed. If a training router is added in the future, restore these tests
and align the paths/response shapes with the actual router implementation.
"""
