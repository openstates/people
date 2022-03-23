# Open States People

![Lint YAML](https://github.com/openstates/people/workflows/Lint%20YAML/badge.svg)

This repository contains YAML files with official information on state legislators, governors, and some municipal leaders.

## Links

* [People Issues](https://github.com/openstates/issues/issues?q=is%3Aissue+is%3Aopen+label%3Adata%3Apeople)
* [Contributor's Guide](https://docs.openstates.org/contributing/)
* [Documentation](https://docs.openstates.org/contributing/people/)
* [Open States Discussions](https://github.com/openstates/issues/discussions)
* [Code of Conduct](https://docs.openstates.org/code-of-conduct/)


## Data Layout

All data within the data directory is organized by state.  Within a given state directory you may find the following:

  * legislature - people that are currently serving in the legislature
  * executive - people that are currently serving in the state executive (e.g. governors)
  * municipalities - people currently serving in local government (e.g. mayors)
  * retired - people not currently serving any tracked roles
  * committees - committee data

## About this Repo

A lot of inspiration was taken from the [congress-legislators](https://github.com/unitedstates/congress-legislators) project that has been maintaining this data for the United States Congress.

New as of 2021: the data/us directory is also directly ported from the congress-legislators repo, reproduced here in our schema for ease of use for people using both data sets.

Historically Open States has scraped this data, but given the relatively infrequent changes and the manual labor required to retire & merge legislators- we have decided to move in this direction in the hopes of improving the data and making it more accessible for contributors.

Also, please note that this portion of the project is in the public domain in the United States with all copyright waived via a [CC0](https://creativecommons.org/publicdomain/zero/1.0/) dedication.  By contributing you agree to waive all copyright claims.
