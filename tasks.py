from invoke import task


def poetry_install(c):
    c.run("poetry install")


@task
def lint(c):
    c.run("poetry run flake8 src --show-source --statistics")
