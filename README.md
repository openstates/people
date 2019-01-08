# Open States People

[![Build Status](https://travis-ci.com/openstates/people.svg?branch=master)](https://travis-ci.com/openstates/people)
[![Coverage Status](https://coveralls.io/repos/github/openstates/people/badge.svg?branch=master)](https://coveralls.io/github/openstates/people?branch=master)

Repository of curated information on all state legislators.


## About the Data

The goal of this project is to maintain a complete & up-to-date picture of everyone serving in state legislatures.  To start we are focusing on data from 2018-onward, but there is no reason why historical data could not be contributed as well.

Much inspiration was taken from the [congress-legislators](https://github.com/unitedstates/congress-legislators) project that has been maintaining this data for the United States Congress.

Historically Open States has scraped this data, but given the relatively infrequent changes and the manual labor required to retire & merge legislators- we have decided to move in this direction in the hopes of improving the data and making it more accessible for contributors.

## Contributing

Please note that this project is in the public domain in the United States with all copyright waived via a [CC0](https://creativecommons.org/publicdomain/zero/1.0/) dedication.  By contributing you agree to waive all copyright claims.

There are a few different scenarios that may be useful:

### Updating legislator data by hand

Let's say you call a legislator and find out that they have a new phone number, contribute back!

See [schema.md](schema.md) for details on the acceptable fields.  If you're looking to add a lot of data but unsure where it fits feel free to ask via an issue and we can either amend the schema or make a recommendation.

0. Start a new branch for this work
1. Make the edits you need in the appropriate YAML file.  Please keep edits to a minimum (e.g. don't re-order fields)
2. Submit a PR, please describe how you came across this information to expedite review.

### Retiring a legislator

0. Start a new branch for this work
1. Run `./scripts/retire.py` on the appropriate legislator file(s)
2. Review the automatically edited files & submit a PR.

### Updating an entire state via a scrape

Let's say a North Carolina has had an election & it makes sense to re-scrape everything for that state.

0. Start a new branch for this work
1. Scrape data using [Open States' Scrapers](https://github.com/openstates/openstates)
2. Run `./scripts/to_yaml.py` against the generated JSON data, this will populate the incoming/ directory 
3. Check for merge candidates using `./scripts/merge.py --incoming nc`
4. Manually reconcile remaining changes, will almost certainly require some retirements as well.
5. Check that data looks clean with `./scripts/lint_yaml.py nc --summary` and prepare a PR.

### Updating a single field for many people

Let's say you want to add foobar_id to a ton of legislators from your own data set or similar.

TBD - We need to create a tool that will aid in this as it will prove a common use case & we can lower the barrier here.

## Scripts

Several scripts are provided to help maintain/check the data.

### to_yaml.py
```
to_yaml.py [OPTIONS] INPUT_DIR

  Convert pupa scraped JSON in INPUT_DIR to YAML files for this repo.

Convert a pupa scrape directory to YAML.  Will put data into incoming/
directory for usage with merge.py's --incoming option.
```

### lint_yaml.py
```
lint_yaml.py [OPTIONS] [ABBREVIATIONS]

  Lint YAML files, optionally also providing a summary of state's data.

  <ABBREVIATIONS> can be provided to restrict linting to select states.

Options:
  -v, --verbose
  --summary / --no-summary  Print summary after validation errors.
```

### merge.py
```
merge.py [OPTIONS]

  Script to assist with merging legislator files.

  Can be used in two modes: incoming or file merge.

  Incoming mode analyzes incoming/ directory files (generated with
  to_yaml.py) and discovers identical & similar files to assist with
  merging.

  File merge mode merges two legislator files.

Options:
  --incoming TEXT  Operate in incoming mode, argument should be state abbr to
                   scan.
  --old TEXT       Operate in merge mode, this is the older of two files &
                   will be kept.
  --new TEXT       In merge mode, this is the newer file that will be removed
                   after merge.
  --keep TEXT      When operating in merge mode, select which data to keep.
                   Values:
                   old
                       Keep data in old file if there's conflict.
                   new
                       Keep data in new file if there's conflict.

                   When omitted, conflicts will raise error.
```

### new_person.py
```
new_person.py [OPTIONS]

Create a new person record.

  Arguments can be passed via command line flags, omitted arguments will be
  prompted.

  Be sure to review the file and add any additional data before committing.

Options:
  --fname TEXT       First Name
  --lname TEXT       Last Name
  --name TEXT        Optional Name, if not provided First + Last will be used
  --state TEXT       State abbreviation
  --district TEXT    District
  --party TEXT       Party
  --rtype TEXT       Role Type
  --url TEXT         Source URL
  --image TEXT       Image URL
  --start-date TEXT  Start Date YYYY-MM-DD
```

### retire.py
```
retire.py [OPTIONS] END_DATE FILENAME

  Retire a legislator, given END_DATE and FILENAME.

  Will set end_date on active roles & committee memberships.
```

### to_database.py
```
to_database.py [OPTIONS] [ABBREVIATIONS]

  Sync YAML files to DB.

Options:
  --purge / --no-purge  Purge all legislators from DB that aren't in YAML.
  --safe / --no-safe    Operate in safe mode, no changes will be written to
                        database.
```

### sync_images.py
```
sync_images.py [OPTIONS] [ABBREVIATIONS]...

  Download images and sync them to S3.

  <ABBR> can be provided to restrict to single state.

Options:
  --skip-existing / --no-skip-existing  Skip processing for files that already exist
                                        on S3. (default: true)
  ```
