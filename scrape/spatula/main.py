import click
import importlib
import pprint
from .utils import Scraper, HtmlListPage


def get_class(dotted_name):
    mod_name, cls_name = dotted_name.rsplit(".", 1)
    mod = importlib.import_module(mod_name)
    return getattr(mod, cls_name)


def _display(obj):
    if isinstance(obj, dict):
        return pprint.pformat(obj)
    elif hasattr(obj, "to_dict"):
        return pprint.pformat(obj.to_dict())
    else:
        return repr(obj)


@click.group()
def cli():
    pass


@cli.command()
@click.argument("class_name")
@click.argument("url", default=None)
def test(class_name, url):
    Cls = get_class(class_name)
    page = Cls(url)
    s = Scraper()
    s.fetch_page_data(page)

    # TODO: better way to check this
    if issubclass(Cls, HtmlListPage):
        for i, item in enumerate(page.get_data()):
            print(f"{i}:", _display(item))
    else:
        print(_display(page.get_data()))


@cli.command()
@click.argument("workflow_name")
def scrape(workflow_name):
    workflow = get_class(workflow_name)
    workflow.execute()


if __name__ == "__main__":
    cli()
