# Open States People

[![Build Status](https://travis-ci.org/openstates/people.svg?branch=master)](https://travis-ci.org/openstates/people)
[![Coverage Status](https://coveralls.io/repos/github/openstates/people/badge.svg?branch=master)](https://coveralls.io/github/openstates/people?branch=master)

Repository of curated information on all state legislators & governors.

This is currently experimental, but is intended as an eventual replacement for running Open States' person scrapers nightly.


## About the Data

The goal of this project is to maintain a complete & up-to-date picture of everyone serving in state legislatures.  To start we are focusing on data from 2018-onward, but there is no reason why historical data could not be contributed as well.

Much inspiration was taken from the [congress-legislators](https://github.com/unitedstates/congress-legislators) project that has been maintaining this data for the United States Congress.

Historically Open States has scraped this data, but given the relatively infrequent changes and the manual labor required to retire & merge legislators- we have decided to move in this direction in the hopes of improving the data and making it more accessible for contributors.

## Contributing

To contribute you can fork this project & submit a PR.  Please try to keep the change as small as possible (i.e. avoid re-ordering keys unnecessarily, etc.) to expedite review.

See [schema.md](schema.md) for details on the acceptable fields.  If you're looking to add a lot of data but unsure where it fits feel free to ask via an issue and we can either amend the schema or make a recommendation.

Please note that this project is in the public domain in the United States with all copyright waived via a [CC0](https://creativecommons.org/publicdomain/zero/1.0/) dedication.  By contributing you agree to waive all copyright claims.

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
lint_yaml.py [OPTIONS] [ABBR]

  Lint YAML files, optionally also providing a summary of state's data.

  <ABBR> can be provided to restrict linting to single state's files.

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

### retire.py
```
retire.py [OPTIONS] END_DATE FILENAME

  Retire a legislator, given END_DATE and FILENAME.

  Will set end_date on active roles & committee memberships.
```

### to_database.py
```
to_database.py [OPTIONS] [ABBR]

  Sync YAML files to DB.

Options:
  --purge / --no-purge  Purge all legislators from DB that aren't in YAML.
  --safe / --no-safe    Operate in safe mode, no changes will be written to
                        database.
```
