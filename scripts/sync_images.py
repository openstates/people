#!/usr/bin/env python
import os
import io
import hashlib
import click
import boto3
from botocore.exceptions import ClientError
import requests
from utils import get_all_abbreviations, iter_objects

ALLOWED_CONTENT_TYPES = ('image/jpeg', 'image/png', 'image/gif', 'image/jpg')


def download_state_images(abbr, skip_existing):
    s3 = boto3.client('s3')
    for person, _ in iter_objects(abbr, 'people'):
        url = person.get('image')
        if not url:
            continue
        person_id = person.get('id')
        key_name = 'images/original/' + person_id

        try:
            obj = s3.head_object(Bucket=os.environ['S3_BUCKET'], Key=key_name)
        except ClientError:
            obj = None

        if obj and skip_existing:
            click.secho(f'{key_name} already exists', fg='green')
            continue

        # get the source URL
        resp = requests.get(url)

        if resp.status_code != 200:
            click.secho(f'could not fetch {url}, {resp.status_code}', fg='red')
            continue

        content_type = resp.headers['content-type']
        if content_type not in ALLOWED_CONTENT_TYPES:
            click.secho(f'unknown content type for {url}, {content_type}', fg='red')
            continue

        # compare sha1 hashes
        sha1 = hashlib.sha1(resp.content).hexdigest()
        if obj and obj['Metadata']['sha1'] == sha1:
            click.secho(f'{key_name} already up to date', fg='yellow')
            continue

        s3.upload_fileobj(
            io.BytesIO(resp.content),
            os.environ['S3_BUCKET'],
            key_name,
            ExtraArgs={
                'Metadata': {'sha1': sha1},
                'ContentType': content_type,
            }
        )
        click.secho(f'copied {url} to {key_name}', fg='green')


@click.command()
@click.argument('abbreviations', nargs=-1)
@click.option('--skip-existing/--no-skip-existing')
def sync_images(abbreviations, skip_existing):
    """
        Download images and sync them to S3.

        <ABBR> can be provided to restrict to single state.
    """
    if not abbreviations:
        abbreviations = get_all_abbreviations()

    for abbr in abbreviations:
        download_state_images(abbr, skip_existing)


if __name__ == '__main__':
    sync_images()
