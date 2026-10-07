---
name: data-review
description: Use when asked to data-review, fact-check, or verify openstates/people person data before merging - the current branch or uncommitted changes against main, or a named state or path - covering role dates, term splits, start/end dates, parties, names, contact details, IDs, retirements, or merged duplicate people.
argument-hint: "[state | path ...] [--base <ref>] [low|medium|high|max] [--fix]"
---

# Data review

The data counterpart of code review: confirm that every fact the current checkout adds, edits,
or deletes in `data/` relative to main is true, and report what to fix before merging.
**Changes no files unless `--fix` is passed.** The one exception is
[term-rules.yml](term-rules.yml), the skill's table of legal term rules: a run that verifies or
corrects a rule writes it back.

**Core rule:** every date and every term split must trace to a source or to the state's legal
rule. A plausible guessed date is the worst error this repo ships, because lint passes it and
nobody looks again.

## Inputs

| Argument | Meaning |
|----------|---------|
| (none) | everything in `data/` the checkout changes vs main: commits, uncommitted and untracked files |
| `ca fl`, `data/de/executive` | limit the review to these states or paths |
| `--base <ref>` | compare with `<ref>` instead of main |
| `low` | only the facts the change makes; no context in touched files |
| `medium` (default) | changed facts + the person's neighbouring roles + repo checks |
| `high` | + every unchanged fact in touched files; with a scope, every file in it |
| `max` | `high`, one research subagent per state, every VERIFIED needs a primary source |
| `--fix` | apply blocker and existing-data fixes after the report |

To review a state's data as it stands (no change at all), give the scope and `high`:
`/data-review de high`.

## 1. Gather

Upstream is the remote whose URL contains `openstates/people` (often `upstream`; `origin` may be
a fork). Call it `$UP`.

```bash
git fetch -q $UP main
BASE=$(git merge-base $UP/main HEAD)            # or the --base ref
git merge-base --is-ancestor $UP/main HEAD && echo rebased || echo "behind main"
git log --format='%h %s%n%b' $BASE..HEAD        # what the commits claim
gh pr view --json number,title,body,mergeable,statusCheckRollup 2>/dev/null   # if the branch has a PR
```

Read every commit message and, if there is one, the **whole** PR description. Match each claim
to the diff:
- a claim with no matching file change: check `$UP/main` (`git log $UP/main --oneline -- <path>`);
  it may have landed already. Report "already on main" or "claimed but missing".
- a change no message mentions: report it.

## 2. Extract claims

```bash
uv run python .claude/skills/data-review/extract_claims.py $BASE [SCOPE...] [--all]
```

One TSV line per fact: file, person, change (added/deleted/moved/edited/unchanged), field, old,
new. Pass `--all` at `high`/`max`. At `medium`, also keep the unchanged roles of each edited
person (a split edits one role and depends on the next). A move to `retired/` and a deleted
file are claims too: "X left office on D", "X duplicates Y".

## 3. Check dates against the rules table

```bash
uv run python .claude/skills/data-review/check_terms.py --self-test
uv run python .claude/skills/data-review/check_terms.py $BASE [SCOPE...] [--all]
```

[term-rules.yml](term-rules.yml) holds each jurisdiction's legal term-start rule with its
citation. `check_terms.py` computes the rule's date (no weekday arithmetic by hand) and gives
every role date a verdict:

| Verdict | Meaning | Action |
|---------|---------|--------|
| `ok` | the legal date | none |
| `repo-conv` | the repo's documented convention, not the legal date | report under housekeeping |
| `MISMATCH` | within 21 days of the rule date | WRONG unless a source shows a mid-term start that day |
| `off-cycle` | far from any rule date | research: special election, appointment, resignation, death |
| `placeholder` | `YYYY-12-31` / `YYYY-01-01` | WRONG; legacy placeholder, never copy it |
| `appointed` | appointed office | research: confirmation or reappointment record per term |
| `no-rule` | no rule for this state/office | research the rule first (below) |
| `merged-terms` | a person file has fewer roles of one type than at the base | BLOCKER: restore the split (see the rule below) |

**Trust a table entry** when it has `cite`, `url` and a `verified` date within the last 2 years:
then the rule is settled and research covers only the person-specific facts. **Re-verify an
entry** (fetch `url`, read the text) when it is missing, has no `cite`/`url`, is older than 2
years, or a primary source for a claim contradicts it (the law may have changed). Write what
you find back into the table:
- rule confirmed: update `verified`.
- law changed: move the old rule into `previous: [{start, until, cite}]` (`until` = the first
  day the new rule applies) and set the new one. Old roles keep checking against the old rule.
- repo consistently follows something else: set `repo:` and explain in `notes`; report it.
- rule doesn't fit the grammar: `start: varies`, the legal text in `notes`, and extend
  `rule_date()` with a self-test case.
Then run `check_terms.py --self-test` again.

With `--all`, legacy data produces a lot of findings: a repo-wide run gives ~15k `MISMATCH`
(mostly `01-01`/`12-31` placeholders, convening dates, and end dates a day before the next
start) and ~5.7k `placeholder`. Report pre-existing findings in section 2 as counts per state
and verdict, and list individually only those the change touches.

Rules that hold everywhere:
- Record the date the term **legally** starts (not the oath, unless that is the legal rule).
- Split terms: term N `end_date` == term N+1 `start_date`.
- A role ends on the day the person's next office starts.
- **Appointed offices have no election cycle.** Every split needs a confirmation or
  reappointment record giving the date; a term length inferred from elsewhere is a guess.
- **One role per term, always.** Never suggest merging terms into one role, even when a split
  date can't be sourced. The fix is the boundary date: give the best-supported date, and mark
  it UNVERIFIABLE with what was searched.

  Worked example (DE State Election Commissioner Anthony Albence): the Senate confirmed him
  2019-06-19 for a 4-year term; no reappointment record was found; elections.delaware.gov says
  his term expires 2028-06-30. Correct: two roles, 2019-06-19 -> 2023-06-19 and
  2023-06-19 -> 2028-06-30, with the second start date marked inferred (UNVERIFIABLE, searched
  news.delaware.gov and Senate nominations). Wrong: one role 2019-06-19 -> 2028-06-30.

## 4. Research in parallel

Dispatch research subagents in one message: one per 2-4 states (`max`: one per state). Skip a
state whose claims are all `ok` dates and nothing else. Each prompt contains, in this order:
1. The exact claims for its states, verbatim from step 2, with each date's verdict from step 3.
2. Each state's table entry (rule, cite, vacancy, notes).
3. The task: verify each non-`ok` claim and every non-date claim (party, name, retirement,
   merge, contact, IDs) with WebSearch/WebFetch; confirm each person still holds the office as
   of today.
4. Source priority: constitution/statute > official .gov press release or roster >
   legislature journal > reputable news > Ballotpedia/Wikipedia (corroboration only).
5. Return format: `claim | VERIFIED / WRONG (correct value) / UNVERIFIABLE | kind of date
   (legal start, oath, confirmation, election) | source URL(s)`.
6. "Do not edit any file."

## 5. Spot-check

For every WRONG that would block the merge, fetch the primary source yourself and confirm it
says what the subagent reported. Downgrade to UNVERIFIABLE if it does not.

## 6. Repo checks

```bash
for check in check_role_dates check_duplicate_people; do
  uv run python .github/scripts/$check.py --base-ref $BASE --changed-files \
    $(git diff --name-only $BASE -- data/) $(git ls-files --others --exclude-standard data/)
done
```

Then check by hand:
- every deleted person's UUID: `git grep <uuid>` hits only `other_identifiers` of the
  surviving record (scheme `openstates`) and `duplicates.md`.
- `duplicates.md`: each resolved group moved under `## Resolved` with the PR number (or the branch name if there is no PR yet).
- retired records keep no office-level email/phone/twitter now used by the current holder.
- no `ids` value (twitter, facebook...) shared across two files.
- dates quoted or unquoted to match the rest of the file; formatting matches the file.
- no overlapping roles of the same type; no role missing `start_date`.

## 7. Report

Sections in this order; omit an empty one:

1. **Wrong data the change adds** (blockers)
2. **Wrong data already in files the change touches** (not blocking; pre-existing)
3. **Description and housekeeping** (messages vs diff, rebase, CI, mergeability, `repo-conv`, step 6)
4. **Unverifiable** (claim, what was searched)
5. **Confirmed correct**, grouped by state, one terse line per person

Every WRONG item: `file` - field - current value -> correct value - rule or source URL - kind of
date. For a split date the correct value is always a date (inferred if need be, and then also
listed under Unverifiable), never "single role" or "merge the terms". End with **Verdict**:
merge / merge after fixes / do not merge, and the fix size (N values in M files).

With `--fix`: apply sections 1 and 2 to the working tree, don't commit. A fix may change
`start_date`/`end_date` values; it may never delete a role to merge terms. When the correct
split date is unknown, keep the split, use the best-supported date, and record UNVERIFIABLE plus
what was searched in the report and in the commit message. Then run
`OS_PEOPLE_DIRECTORY=./ uv run os-people lint <st>...` for the touched states and
`check_terms.py` again, and report both results.

## Red flags in a diff

| Pattern | Why it's suspect |
|---------|------------------|
| A role split into two at a round 2- or 4-year boundary | Often guessed; demand the source for the split date |
| Split of an appointed office | Needs a confirmation/reappointment record, not a term length |
| Same date on unrelated people | Batch date, not each person's own |
| `12-31` / `01-01` dates | Placeholder |
| Description says "retired X", diff doesn't | Already on main, or missing |
| `end_date` in the future on a split term | Statutory end; confirm against the official site |
| Role count for a person+office drops between base and head (two terms merged into one) | BLOCKER. Terms are never combined; restore the split and fix the boundary date instead. `check_terms.py` reports it as `merged-terms` |

## Common mistakes

- Applying a rule from memory instead of the table. The rule you remember may be the
  statewide rule, not the legislative one.
- Computing weekdays by hand. Use `check_terms.py`.
- Treating Wikipedia/Ballotpedia agreement as VERIFIED for a date. They copy each other.
- Reporting pre-existing problems as blockers. They go in section 2.
- Reading only the summary bullets of the PR description or commit messages.
- Editing files without `--fix`.
- Suggesting a merge of two terms as the fix for an unsourced split.
