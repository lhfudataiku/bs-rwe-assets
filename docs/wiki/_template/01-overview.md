<span id="version" style="color: grey; float: right">Version {{version}}</span><br/>

<div class="alert">
<b>Internal use only. SYNPUF licence restriction:</b> this project holds CMS DE-SynPUF data in OMOP
and Athena vocabularies. Do not install it on customer instances, export its data or share bundles
outside Dataiku. See the Legal article.
</div>

### RWD/RWE Solution Demo Assets
- **Part 1: OMOP Data Foundation** (this project)
- Part 2: RWD Cohort Discovery Solution
- Part 3: Real World Evidence

This project is part 1 of the RWD/RWE demo assets. Role: **{{role}}** · Sample: **{{sample_size}}** ·
Storage: **{{connection}}**{{upstream_sentence}}

# Project Scope & Value
This project provides the 15 OMOP CDM tables the RWD Cohort Discovery solution reads (13 standard
tables plus `concept` and `concept_ancestor`), harmonised to the solution's v1.1 schema: lowercase
column names, `dateonly` for OMOP DATE, `datetimenotz` for DATETIME and integer ids.

# How to use
Set the solution's `data_preparation_project_key` to `{{project_key}}` and map the 15 table variables
to the datasets in the `OMOP CDM export` zone. Run the solution's "Check OMOP CDM Schema" scenario first.

# Owner
{{owner}}
