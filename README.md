Open States People
===================

Repository of curated information on all state legislators & governors.

This is currently experimental, but is intended as an eventual replacement for running Open States' person scrapers nightly.


About the Data
--------------

The goal of this project is to maintain a complete & up-to-date picture of everyone serving in state legislatures.  To start we are focusing on data from 2018-onward, but there is no reason why historical data could not be contributed as well.

Much inspiration was taken from the [congress-legislators](https://github.com/unitedstates/congress-legislators) project that has been maintaining this data for the United States Congress.

Historically Open States has scraped this data, but given the relatively infrequent changes and the manual labor required to retire & merge legislators- we have decided to move in this direction in the hopes of improving the data and making it more accessible for contributors.

Scripts
-------

Several scripts are provided to help maintain/check the data.

```./scripts/to_yaml.py <data-dir>```

Convert a pupa scrape directory to YAML.  (currently will wipe all data from destination directory)

```./scripts/lint_yaml.py <files>```

Check status of YAML files.
