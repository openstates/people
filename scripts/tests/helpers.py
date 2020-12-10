from os import path

def fixture_path(p: str) -> str:
    return path.abspath(
        path.join(path.dirname(__file__), 
        "fixtures",
        p)
    )


