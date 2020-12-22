# spatula (next-gen scrape) 2.0

## Motivations

- Scrapers should be easy to write and understand.
- It should be possible to scrape a single item for incremental scraping and testing during development.
- To this end, providing an interface that makes this not only possible, but makes the opposite harder, seems like a good idea.

## Observations

There are four types of pages we generally encounter:

- 'Listing' pages (e.g. a list of all legislators in a chamber or all bills in a session)
  - Note: Sometimes these are paginated.
- 'Detail' pages (e.g. a page with a person's biographical information or a bill's status updates and relevant links)
- 'Auxillary Detail' pages that augment detail information (e.g. a list of versions loaded from a separate page)
- 'Augmentation' pages that provide data that complements the entire data set.  (e.g. a page mapping bills to their subjects, often scraped first and stored in a dictionary that is referenced by each bill as it is scraped)

## Philosophy

Generally speaking, we want to enforce some best practices by making it easiest to do the right thing.

So combining our motivations & observations, arriving at:

- One class or function per type of page.
- Listing Pages are responsible for returning a list of things to get details on. (and nearly nothing else, see question #2)
- Detail pages are responsible for returning built objects (i.e. Person, Bill, etc.) that are as complete as possible.
- Detail pages can call auxillary page scrapers as needed.  These classes simply return dictionaries of data to add.
- Augmentation pages can provide data that will be grafted onto the entire data set, but should be used sparingly.

## Example

Let's say a hypothetical state has the following pages:

- listing of all senators
- listing of all reps
  - all people happen to use nearly identical pages regardless of chamber
- list of all bills (possibly paginated?)
  - detail page for a given bill
    - detail page for a given vote, linked from bills (0 or more per bill)
- another separate page that lists all bill ids for current session under given subjects (information not available on bill pages)

We'd go about writing this by writing individual classes, perhaps:

- SenateRoster - listing of all senators
- HouseRoster - listing of all reps
- PersonDetail - all people happen to use nearly identical pages regardless of chamber
- BillList - list of all bills (possibly paginated?)
- BillDetail - detail page for a given bill
- VoteDetail - detail page for a given vote, linked from bills (0 or more per bill)
- SubjectListing - aux. page that lists all bill ids for current session under given subjects

## Proposed API


## Tangent: Selectors



## Proposed Usage

While developing, the following commands are available (spatula is the stand-in name for the CLI entrypoint):

`spatula test md.SenateRoster` - Will print a list of all data yielded from the SenateRoster page.
`spatula test md.PersonDetail https://example.com/123` - Will print result of using PersonDetail scraper on given URL.
`spatula run md.house_members_workflow` - Will run a defined 'Workflow' which is a configuration of an entrypoint.  Details TBD.


## Open Questions

1. How do we want to handle pagination?  This is a special case where a list scraper should do multiple fetches.

2. Should listing pages be able to hand additional information to detail pages they invoke?  There are cases where it is hard (impossible?) to get certain information on a detail page but easy from the listing.  (Example is chamber information in Maryland legislators.)

3. How do augmentation pages work?  Should this happen magically or should the user be required to map aux. data to bills as happens now?

4. What edge cases are we aware of that seem hard to implement in this structure? 

5. Lots of things aren't named very well yet as concepts evolve. Clearer names are more than welcome.
