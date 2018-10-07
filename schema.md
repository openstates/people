The following fields are available:

* id: UUID representing this person for this data set.  **required**
* name: Full Name.  **required**
* given_name: First name.
* family_name: Last name.
* gender: Male/Female/Other
* biography: Official biography text.
* birth_date: Birth date in YYYY-MM-DD format.
* death_date: Death date in YYYY-MM-DD format.
* image: URL to official photo.
* ids:  nested dictionary of additional ids
    * twitter: username of official Twitter account
    * youtube: username of official YouTube account
    * instagram: username of official Instagram account
    * facebook: username of official Facebook account
    * legacy_openstates: legacy Open States ID (e.g. NCL000123)

### List Fields

These sections can have a list of objects, each with the following fields available.

* contact_details: 
    * note: Description of what these details refer to (e.g. "District Office").  **required**
    * address: Mailing address.
    * email: Email address.
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
    * start_date: optional date name started being valid for this person
    * end_date: optional date name ceased to be valid for this person

* sources:
    * note: description of the usage of this source
    * url: URL used to collect information for this person **required**

### Roles

These sections describe roles that the legislator had.
All include optional start_date & end_date fields that can be used to scope a person's membership on a committee, party, or particular legislative role.

* committees:
    * name:   Name of the committee.  **required**
    * post:   Special role fulfilled, if not a typical committe member. (e.g. chair)
    * start_date
    * end_date

* party:
    * name: Name of the party.    **required**
    * start_date
    * end_date

* roles:
    * type: upper|lower|legislature|gov|lt_gov    **required**
    * district: name/number of district   **required if not gov/lt_gov**
    * jurisdiction: ocd-jurisdiction identifier **required**
    * start_date
    * end_date
    * contact_details:    It is possible to list any role-specific contact details here and they will be considered inactive when the role ends.

### Additional Fields

These fields should only be set by the automated processes, but may also be present.
* summary
* sort_name
* extras
