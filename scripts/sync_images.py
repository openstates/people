#!/usr/bin/env python
import os
import io
import hashlib
import click
import boto3
import typing
from PIL import Image
from botocore.exceptions import ClientError
import requests
from utils import get_all_abbreviations, iter_objects


ALLOWED_CONTENT_TYPES = ("image/jpeg", "image/png", "image/gif", "image/jpg")
s3 = boto3.client("s3")


_IMAGE_RETURN_TYPE = tuple[typing.Optional[bytes], typing.Optional[str]]


def upload(
    img_callable: typing.Callable[[], _IMAGE_RETURN_TYPE], key_name: str, skip_existing: bool
) -> typing.Optional[bytes]:
    """upload works as a sort of decorator around img_callable, which is
    only called if necessary after checking if there's already an image"""
    try:
        obj = s3.head_object(Bucket=os.environ["S3_BUCKET"], Key=key_name)
    except ClientError:
        obj = None

    if obj and skip_existing:
        click.secho(f"{key_name} already exists", fg="yellow")
        return None

    # if we need to get the object, call the (potentially expensive) callable
    img_bytes, content_type = img_callable()
    if not img_bytes:
        return None

    # compare sha1 hashes
    sha1 = hashlib.sha1(img_bytes).hexdigest()
    if obj and obj["Metadata"].get("sha1") == sha1:
        click.secho(f"{key_name} already up to date", fg="yellow")
        return img_bytes

    click.secho(f"uploading {key_name}", fg="green")
    s3.upload_fileobj(
        io.BytesIO(img_bytes),
        os.environ["S3_BUCKET"],
        key_name,
        ExtraArgs={"Metadata": {"sha1": sha1}, "ContentType": content_type, "ACL": "public-read"},
    )

    # return the raw bytes, which may be reused for resizing/etc.
    return img_bytes


def download_image(url: str) -> _IMAGE_RETURN_TYPE:
    try:
        resp = requests.get(url)
    except Exception as e:
        click.secho(f"could not fetch {url}, {e}", fg="red")
        return None, None

    if resp.status_code != 200:
        click.secho(f"could not fetch {url}, {resp.status_code}", fg="red")
        return None, None

    content_type = resp.headers["content-type"]
    if content_type not in ALLOWED_CONTENT_TYPES:
        click.secho(f"unknown content type for {url}, {content_type}", fg="red")
        return None, None

    return resp.content, content_type


def resize_image(img_bytes: bytes, size: int) -> _IMAGE_RETURN_TYPE:
    img = Image.open(fp=io.BytesIO(img_bytes))
    img = img.convert("RGB")
    img.thumbnail((size, size))
    output = io.BytesIO()
    img.save(output, "JPEG", quality=80, progressive=True)
    output.seek(0)
    return output.read(), "image/jpeg"


def download_state_images(abbr: str, skip_existing: bool) -> None:
    for person, _ in iter_objects(abbr, "legislature"):
        url = person.get("image")
        person_id = person["id"]
        if not url:
            continue

        # safe to cast because we've bailed above if url is None
        img_bytes = upload(
            lambda: download_image(typing.cast(str, url)),
            f"images/original/{person_id}",
            skip_existing,
        )
        # if the image got skipped, we can't do the resizes either, this means if we add new
        # profiles we need to run with --no-skip-existing
        if not img_bytes:
            continue

        # resize image so largest dimension is 200px
        upload(
            lambda: resize_image(typing.cast(bytes, img_bytes), 200),
            f"images/small/{person_id}",
            skip_existing,
        )


# def recognize(key):
#     client = boto3.client('rekognition')
#     resp = client.detect_faces(Image={'S3Object': {'Bucket': os.environ['S3_BUCKET'],
#                                                'Name': key}},
#                            Attributes=["DEFAULT"])
# algorithm suggested here seems like a good starting point
# https://stackoverflow.com/questions/4813608/cropping-an-image-with-a-focus-area-face-using-imagemagick


@click.command()
@click.argument("abbreviations", nargs=-1)
@click.option(
    "--skip-existing/--no-skip-existing",
    help="Skip processing for files that already exist on S3. (default: true)",
)
def sync_images(abbreviations: list[str], skip_existing: bool) -> None:
    """
    Download images and sync them to S3.

    <ABBR> can be provided to restrict to single state.
    """
    if not abbreviations:
        abbreviations = get_all_abbreviations()

    for abbr in abbreviations:
        download_state_images(abbr, skip_existing)


if __name__ == "__main__":
    sync_images()
