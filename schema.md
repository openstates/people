# Person Schema

* id: UUID representing this person for this data set.  **required**
* name: Full Name.  **required**
* given_name: First name.
* family_name: Last name.
* middle_name: Middle name or initial.
* suffix: Name Suffix.
* gender: Male/Female/Other
* email: Email address.
* biography: Official biography text.
* birth_date: Birth date in YYYY-MM-DD format.
* death_date: Death date in YYYY-MM-DD format.
* image: URL to official photo.
* ids:  nested dictionary of additional ids
    * twitter: username of official Twitter account
    * youtube: username of official YouTube account
    * instagram: username of official Instagram account
    * facebook: username of official Facebook account
* party: list of parties that the legislator has been a part of, each may have the following fields:
    * name: Name of the party.    **required**
    * start_date
    * end_date
* roles: list of legislative & executive roles held by this individual, each may have the following fields:
    * type: upper|lower|legislature|governor|lt_governor|mayor    **required**
    * district: name/number of district   **required if upper|lower|legislature**
    * jurisdiction: ocd-jurisdiction identifier **required**
    * start_date  **required if not upper|lower|legislature**
    * end_date    **required if not upper|lower|legislature**
    * end_reason: reason this role ended, such as resignation/death
* extras - unvalidated JSON to store additional details in
* contact_details (see below)
* links (see below)
* other_identifiers (see below)
* other_names (see below)
* sources (see below)

# Committee Schema

* id: UUID representing this organization.  **required**
* jurisdiction: ocd-jurisdiction identifier **required**
* name: Name of Committee.  **required**
* chamber: Chamber of this committee, can be:
    * upper
    * lower
    * legislature
    **required**
* classification: Classification, can be:
    * committee
    * subcommittee
    **required**
* parent: `id` of parent committee, if classification is subcommittee.
* members: list of memberships, each may have the following:
    * id - ocd-person ID if known
    * name - name of person **required**
    * role - role that person fills on committee, if not 'member'
    * start_date - optional start date of this membership
    * end_date - optional end date of this membership
* links (see below)
* sources (see below)
* other_names (see below)

### Common Elements

These sections can have a list of objects, each with the following fields available.

* contact_details:
    * note: "District Office" or "Capitol Office"  **required**
    * address: Mailing address.
    * voice: Phone number used for voice calls.
    * fax: Fax number.

* links:
    * note: description of the purpose of this link
    * url: URL associated with legislator **required**

* other_identifiers:
    * scheme: origin of this identifier (e.g. "votesmart")        **required**
    * identifier: identifier used by the given service/scheme (e.g. 13823)    **required**
    * start_date: optional date identifier started being valid for this person
    * end_date: optional date identifier ceased to be valid for this person

* other_names:
    * name: alternate name that has been seen for this person **required**
        * if a new name has strange spacing, you must quote the entire entry
        * e.g. `name: "Stephanie  T. Bolan"` vs. `name: Stephanie  T. Bolan`
        * If you neglect to do this, yaml _will_ remove additional spaces
    * start_date: optional date name started being valid for this person
    * end_date: optional date name ceased to be valid for this person

* sources:
    * note: description of the usage of this source
    * url: URL used to collect information for this person **required**
