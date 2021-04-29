from invoke import task
import os


def poetry_install(c):
    c.run("poetry install")


@task
def test(c, args=""):
    os.environ["PYTHONPATH"] = "."
    c.run(
        "poetry run pytest --cov src/ --cov-report html --ds=tests.django_test_settings " + args,
        pty=True,
    )
