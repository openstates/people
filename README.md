# Open States People

[![Build Status](https://travis-ci.com/openstates/people.svg?branch=master)](https://travis-ci.com/openstates/people)
[![Coverage Status](https://coveralls.io/repos/github/openstates/people/badge.svg?branch=master)](https://coveralls.io/github/openstates/people?branch=master)

This repository contains YAML files with all the information on given individuals, as well as scripts to work with & maintain the data.

## Links

* [People Issues](https://github.com/openstates/issues/issues?q=is%3Aissue+is%3Aopen+label%3Adata%3Apeople)
* [Contributor's Guide](https://docs.openstates.org/en/latest/contributing/getting-started.html)
* [Documentation](https://docs.openstates.org/en/latest/contributing/people.html)
* [Open States Discourse](https://discourse.openstates.org)
* [Code of Conduct](https://docs.openstates.org/en/latest/contributing/code-of-conduct.html)

## Running Tests

    docker-compose run --rm --entrypoint scripts/run_tests.sh people

## Data Layout

All data within the data directory is organized by state.  Within a given state directory you may find the following:

  * legislature - people that are currently serving in the legislature
  * municipalities - people currently serving in local government (e.g. mayors)
  * retired - people not currently serving any tracked roles
  * committees - committee data (future TBD)

## About this Repo

A lot of inspiration was taken from the [congress-legislators](https://github.com/unitedstates/congress-legislators) project that has been maintaining this data for the United States Congress.

Historically Open States has scraped this data, but given the relatively infrequent changes and the manual labor required to retire & merge legislators- we have decided to move in this direction in the hopes of improving the data and making it more accessible for contributors.

Also, please note that this portion of the project is in the public domain in the United States with all copyright waived via a [CC0](https://creativecommons.org/publicdomain/zero/1.0/) dedication.  By contributing you agree to waive all copyright claims.
