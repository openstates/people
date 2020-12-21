import click
import importlib
from spatula.utils import Scraper


def get_class(dotted_name):
    mod_name, cls_name = dotted_name.rsplit(".", 1)
    mod = importlib.import_module(mod_name)
    return getattr(mod, cls_name)


@click.group()
def cli():
    pass


@cli.command()
@click.argument("class_name")
@click.argument("url")
def sample(class_name, url):
    Cls = get_class(class_name)
    page = Cls(url)
    s = Scraper()
    s.fetch_page_data(page)
    print(page.get_data())


@cli.command()
@click.argument("class_name")
@click.option("--chamber", multiple=True, default=["upper", "lower"])
@click.option("--session", default=None)
def scrape(class_name, chamber, session):
    Cls = get_class(class_name)
    for ch in chamber:
        for item in Cls().scrape(ch, session):
            item.save("incoming/md/people")


@cli.command()
@click.argument("class_name")
def list(class_name):
    s = Scraper()
    Cls = get_class(class_name)
    obj = Cls()
    s.fetch_page_data(obj)
    for i, item in enumerate(obj.get_data()):
        print(f"{i}:", item)


if __name__ == "__main__":
    cli()
