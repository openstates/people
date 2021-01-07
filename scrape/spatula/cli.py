import attr
import click
import importlib
import pprint
from .core import Scraper
from .pages import ListPage


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
@click.option("-i", "--interactive")
@click.option("-d", "--data", multiple=True)
def test(class_name, interactive, data):
    Cls = get_class(class_name)
    s = Scraper()

    # build fake input from command line data if present
    fake_input = {}
    for item in data:
        k, v = item.split("=", 1)
        fake_input[k] = v

    input_type = getattr(Cls, "input_type", None)
    if input_type:
        print(f"{Cls.__name__} expects input ({input_type.__name__}): ")
        for field in attr.fields(input_type):
            if field.name in fake_input:
                print(f"  {field.name}: {fake_input[field.name]}")
            elif interactive:
                fake_input[field.name] = click.prompt("  " + field.name)
            else:
                dummy_val = f"~{field.name}"
                fake_input[field.name] = dummy_val
                print(f"  {field.name}: {dummy_val}")

        page = Cls(input_type(**fake_input))
    else:
        page = Cls(fake_input)

    # fetch data after input is handled, since we might need to build the source
    s.fetch_page_data(page)

    if issubclass(Cls, ListPage):
        for i, item in enumerate(page.get_data()):
            print(f"{i}:", _display(item))
    else:
        print(_display(page.get_data()))


@cli.command()
@click.argument("workflow_name")
@click.option("-o", "--output-dir", default=None)
def scrape(workflow_name, output_dir):
    workflow = get_class(workflow_name)
    workflow.execute(output_dir=output_dir)


if __name__ == "__main__":
    cli()
