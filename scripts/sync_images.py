#!/usr/bin/env python
import os
import io
import hashlib
import click
import boto3
from botocore.exceptions import ClientError
import requests
from utils import get_all_abbreviations, iter_objects


def download_state_images(abbr):
    s3 = boto3.client('s3')
    for person, _ in iter_objects(abbr, 'people'):
        url = person.get('image')
        person_id = person.get('id')
        resp = requests.get(url)

        if resp.status_code != 200:
            click.secho(f'could not fetch {url}, {resp.status_code}', fg='red')
            continue

        sha1 = hashlib.sha1(resp.content).hexdigest()
        key_name = 'images/original/' + person_id

        try:
            obj = s3.head_object(Bucket=os.environ['S3_BUCKET'], Key=key_name)

            if obj['Metadata']['sha1'] == sha1:
                click.secho(f'{key_name} already up to date', fg='yellow')
                continue
        except ClientError:
            pass

        s3.upload_fileobj(
            io.BytesIO(resp.content),
            os.environ['S3_BUCKET'],
            key_name,
            ExtraArgs={
                'Metadata': {'sha1': sha1},
                'ContentType': resp.headers['content-type'],
            }
        )
        click.secho(f'copied {url} to {key_name}', fg='green')


@click.command()
@click.argument('abbreviations', nargs=-1)
def sync_images(abbreviations):
    """
        Download images and sync them to S3.

        <ABBR> can be provided to restrict to single state.
    """
    if not abbreviations:
        abbreviations = get_all_abbreviations()

    for abbr in abbreviations:
        download_state_images(abbr)


if __name__ == '__main__':
    sync_images()
