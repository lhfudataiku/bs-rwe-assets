# Real-World Evidence Governance — Review of Regulation, Literature and Market (US and EU)

Nov 13, 2026 · @Li-Heng Fu

> **Lifecycle:** Reference (evidence base for `governance-mvp-proposal.md`; dated, not maintained
> continuously) · **Part:** all · **Audience:** suite owner, asset owners, governance and QA leads,
> account team · **Authority:** what regulators, the literature and the market ask of RWE governance as of
> 2026-11-13; it proposes nothing itself · **Update when:** a guidance listed as draft is finalised, an
> EHDS implementing act is adopted, or the proposal's regulatory mapping is revised.

## Summary

Governance of real-world evidence (RWE) is mostly governance of the **study**: the question, the
fitness of the data for that question, the protocol, the operational definitions, the design diagnostics
and the release of results. Platform controls (access, audit trail, lineage, validated systems) are
required, but they are the base layer and every serious vendor already claims them.

Three findings carry the review:

1. **Regulators on both sides ask for the same study artefacts.** A protocol and analysis plan fixed
   before the outcome analysis, a documented fit-for-purpose assessment of the data source, validated
   operational definitions, and traceability from source data to result. ICH M14 now states this in one
   text for the US and the EU.
2. **Published reviews of regulatory decisions attribute rejected RWE to design and data relevance**:
   confounding, selection bias, misclassification, missing data. None of the reviews found cite access
   control or lineage as a cause.
3. **No vendor found joins the pieces in one inspectable record**: data-use permission, fitness
   assessment, protocol and phenotype lock, code promotion and results release. RWE platforms govern
   inside their own tool; data science platforms govern models.

## Method and confidence

Web research on 2026-11-13 across four strands: US regulation, EU regulation, peer-reviewed and
recognised-body literature, and vendor and buyer material. Confidence differs by strand, and each claim
below carries a mark:

| Mark | Meaning |
| --- | --- |
| **[P]** | Read on a primary source this session (regulator page, guidance text, journal record) |
| **[S]** | Secondary source only (law-firm note, trade press, search summary) |
| **[R]** | From recall of a well-known source; check volume, pages or article number before quoting |

Limits: EUR-Lex returned no readable text, so EHDS article-level detail is [R] or [S]. Market evidence
is mostly vendor marketing. No named-pharma internal operating model was found in a primary source.

## 1. United States

### What applies

| Instrument | Status | What it asks for |
| --- | --- | --- |
| Cures Act s.3022 / FD&C 505F; FDA RWE Framework (2018) | In force [P] | Creates the RWE Program. No platform obligation by itself; the guidances implement it |
| *Considerations for the Use of RWD and RWE* | Final, Aug 2023 [P] | Protocol and analysis plan finalised before the pre-specified analyses, revisions date-stamped with a rationale; analyses outside the plan labelled exploratory; audit trail from extraction to retained datasets (user access, data changes, protocol changes, analyses run); patient-level data deliverable to FDA, with data-owner agreements for inspection; sponsor systems should comply with Part 11 |
| *Assessing EHR and Medical Claims Data* | Final, Jul 2024 [P] | Reliability = accuracy, completeness, traceability. Conceptual and operational definitions in the protocol; operational definitions validated (sensitivity, specificity, PPV, NPV) and reassessed on a new source or period; QA/QC plan with reproducible steps; every retrieval and transformation documented, including conversion to a common data model; annotated programs |
| ICH M14 (non-interventional studies using RWD) | FDA final, Mar 2026 [P] | Research question, fit-for-purpose data source, variable definitions, bias and confounding, analysis, reporting. Section-level text not read [R] |
| *Electronic Systems, Records and Signatures: Q&A* (Part 11) | Final, Oct 2024 [P] | FDA does not assess the RWD source system; Part 11 applies once the record enters the sponsor's system. Audit trails capture create, modify, delete and cannot be disabled; validation is risk-based and inspectable |
| ICH E6(R3) section 4, data governance | FDA final, Sep 2025 [P] | Audit trails and metadata interpretable and not disabled; validated transfers; user management. Written for trials; applies by analogy |
| *RWE for Medical Devices* | Final, Dec 2025 [P] | Provenance; retain the source-to-CDM transformation; audit trail from the first data available to the sponsor |
| *AI to Support Regulatory Decision-Making for Drugs* | Draft, Jan 2025 [P] | Seven-step credibility framework by context of use |
| FDA-EMA *Guiding Principles of Good AI Practice in Drug Development* | Jan 2026, non-binding [P] | Ten principles: context of use, data governance and documentation, lifecycle management |
| HIPAA de-identification, 45 CFR 164.514 | Unchanged [P] | Expert Determination or Safe Harbor; re-identification code rules |

### What is moving

- **Patient-level data.** In December 2025 FDA said it would accept RWE without identifiable
  patient-level data for certain device submissions. For drugs the requirement stands; a request for
  information published 12 Nov 2026 (docket FDA-2026-N-10742, comments to 11 Jan 2027) reopens it. [P]
- **PDUFA VIII** (proposed, Aug 2026) ends the standalone RWE pilot and adds no sponsor governance
  duty. [P]
- Still draft: externally controlled trials (2023), non-interventional studies (2024), the AI guidance. [P]
- Computer Software Assurance (final Sep 2025) covers device production software. It is a model for
  risk-based validation, not a requirement on RWE analytics. [P]

### Operating exemplar

FDA Sentinel keeps data with the partners, converts locally to a common data model and returns
de-identified results. Each data refresh passes three levels of quality review (completeness and
validity, cross-table consistency, comparison with the previous refresh) before it is approved for use.
[P] The point for this suite: a refresh is a governed event, not a background job.

## 2. European Union

### What applies

| Instrument | Status | What it asks for |
| --- | --- | --- |
| ICH M14 | Effective in the EU 18 Mar 2026 [P] | As above |
| EMA reflection paper on RWD in non-interventional studies (EMA/99865/2025) | Final, Mar 2025 [P]; content [S] | Feasibility assessment; pre-specified protocol and analysis plan; target trial emulation for causal questions; data-quality characterisation; registration; public protocol and code |
| HMA-EMA Catalogues of RWD sources and studies | Live since Feb 2024 [P] | Registration required for imposed post-authorisation safety studies; expected for others |
| HMA-EMA Data Quality Framework (2023) and its RWD chapter | RWD chapter "considered adopted", Dec 2025 minutes [P] | Separates reliability from relevance; quality is assessed against the intended use |
| GVP Module VIII (post-authorisation safety studies) | Rev 3 current; Rev 4 planned [P] | Protocol, registration, final report |
| GDPR Art. 6, 9(2)(j), 89 | In force [R] | Legal basis, Art. 9 condition, safeguards: minimisation, pseudonymisation |
| EHDS, Regulation (EU) 2025/327 | In force 26 Mar 2025; secondary use applies 26 Mar 2029 (some categories 2031) [P] | See below |
| EU HTA Regulation 2021/2282 | Joint clinical assessments since 12 Jan 2025 for oncology and advanced therapies [P] | Non-randomised evidence needs pre-specification and confounder adjustment [S] |
| AI Act, Regulation (EU) 2024/1689 | High-risk obligations delayed to 2 Dec 2027 (Annex III) [P] | Research exemption, Art. 2(6) [R] |

### European Health Data Space

From 2029 the EHDS changes how data is reached, which is a platform matter:

- Access only through a **data permit** from a health data access body, for a listed purpose. [P]
- Processing only inside a **secure processing environment**; person-level data cannot be
  downloaded. [P]
- Named users, access logs, permit duration limits, no re-identification, results made public
  (18 months). [R]
- A data quality and utility label for publicly funded datasets (Art. 78). [P]
- Implementing acts are due by 26 Mar 2027. The dataset-metadata act (27 elements, HealthDCAT-AP) was
  reported adopted in Sept 2026 [S]; the secure-environment and label acts were not found.

### What is moving

- EDPB guidelines on scientific research (1/2026), anonymisation (02/2026) and pseudonymisation
  (01/2025) are all still consultation versions. [P]
- The Digital Omnibus change to GDPR is not adopted. [S]
- The Annex 11 revision and new Annex 22 (AI) are still drafts and GMP-scoped: a validation benchmark,
  not a requirement on RWE analytics. [P]
- The pharma package is provisionally agreed but not published. [S]
- Whether a propensity model in a non-interventional study is "high-risk" under the AI Act: it does not
  match an Annex III use case, but no primary source states this. Treat as a reading.

### Operating exemplar

DARWIN EU runs on OMOP with about 40 data partners. EMA's fourth RWE experience report (Feb 2025 to
Feb 2026) counts 108 topics and 88 studies, and reports close to 80% feasibility once questions are
screened for feasibility up front. In the first report, infeasibility came mostly from data that did
not capture the needed variables. [P] Feasibility screening is the control that changed the outcome.

## 3. Literature

### Reproducibility needs executable specifications

- **REPEAT** (Wang et al., *Nat Commun* 2022, doi:10.1038/s41467-022-32310-3): 150 studies reproduced,
  250 assessed for reporting. Effect sizes correlated at r = 0.85, but an attrition table appeared in
  54%, a design diagram in 8%, and analytic code was referenced in 7%. Only 3 of 250 studies could be
  reproduced without assumptions. [P]
- **Ostropolets et al.** (*JAMIA* 2023, doi:10.1093/jamia/ocad009): nine expert teams, same data, tools
  and written methods. Cohorts ranged from 2,159 to 63,619 patients against a reference of 6,196. [P]
- **RCT-DUPLICATE** (Wang et al., *JAMA* 2023, doi:10.1001/jama.2023.4221): 32 trials emulated,
  r = 0.82; agreement was higher where the trial design could be emulated closely. [P]
- Templates that close the gap: HARPER (Wang et al., *PDS* 2023), STaRT-RWE (*BMJ* 2021), RECORD-PE
  (*BMJ* 2018), the TARGET guideline for target trial emulation (*JAMA* 2025). [R, TARGET P]

### Data quality is not fitness for purpose

- The Kahn framework (2016) and the OHDSI Data Quality Dashboard (Blacketer et al., *JAMIA* 2021) check
  conformance, completeness and plausibility of a **database**. [R]
- SPACE and SPIFD (Gatto et al., *Clin Pharmacol Ther* 2019, 2022, 2023), NICE's RWE framework with
  DataSAT (2022) and the EMA framework ask a different question: are exposure, outcome and key
  confounders captured well enough, with enough follow-up and sample, for **this study**. [R]

### Design diagnostics decide credibility

- Target trial emulation (Hernán and Robins, *Am J Epidemiol* 2016) fixes time zero, eligibility and
  treatment strategies before analysis. [R]
- Negative-control outcomes and empirical calibration (Schuemie et al., *Stat Med* 2014; *PNAS* 2018)
  measure residual systematic error. [P, R]
- OHDSI's LEGEND principles (Schuemie et al., *JAMIA* 2020): pre-specify, run all analyses, publish all
  results and diagnostics, share code. Diagnostics (covariate balance, equipoise) are judged against
  thresholds fixed before the results are seen. [R]

### Phenotypes drift

- PheValuator (Swerdel et al., *J Biomed Inform* 2019, 2022) estimates sensitivity and PPV without
  chart review. [R]
- Vocabulary upgrades can change a concept set silently; one definition gained 179 concepts between
  versions. Evidence is OHDSI conference abstracts (2022, 2025), not peer-reviewed. [P]

### Why regulators reject RWE

- Purpura et al. (*Clin Pharmacol Ther* 2022): of 88 FDA approvals containing RWE studies, 15% were
  judged inadequate and 11% were not addressed in the review. Reasons: confounding, selection and
  immortal-time bias, misclassification, missing data, sample size, no patient-level data. [P]
- Vaghela et al. (*Orphanet J Rare Dis* 2024): FDA criticised the RWD in 11 of 20 rare-disease
  applications. [P]

### AI in RWE generation

- GPT-3.5 and GPT-4 produced about 32–38% hallucinated codes when asked for phenotype code lists
  (Tekumalla and Banda, *Genomics Inform* 2024). [P]
- ELEVATE-GenAI (ISPOR, *Value Health* 2025) gives ten reporting domains, not yet validated. [P]

### Not evidenced

No peer-reviewed data was found on contracting or licence delays, or on sign-off fatigue. Both are
widely stated by practitioners; this review cannot put a number on them.

## 4. Market

### Table stakes

- **Audit trail, protocol locking, versioning, role-based access.** Aetion (part of Datavant since
  July 2025) claims tamper-proof audit trails and protocol locking [P]; Truveta flags a study at
  creation as intended for regulatory submission [S].
- **Security attestations.** ISO 27001, SOC 2 and HITRUST are the baseline (TriNetX, Truveta). [S]
- **Shared-responsibility wording on validation.** Domino says "designed to support" GxP; Databricks'
  GxP whitepaper says the customer validates. [P] Dataiku's GxP workflows page (3 Sept 2026) sells a
  Good Machine Learning Practice template with recorded sign-offs and does not mention Part 11. [P]
- **OMOP and OHDSI tooling as the quality layer.** [S]

### Differentiators

- **Measured data reliability.** Verantos quantifies accuracy, completeness and traceability; Flatiron
  frames "regulatory-grade" as earned per research question. [S]
- **Purpose-based access.** Palantir Foundry checks each data request against a declared purpose. [S]
- **Secure environments positioned for the EHDS.** Lifebit, BC Platforms. [S]

### Whitespace

No vendor found publicly ties data-use permission, fitness assessment, protocol and phenotype version
sign-off, gated promotion of analysis code and results release into one record across tools. This is
an absence of evidence in public material, not proof that no one does it.

### Buyer signals

| Source | Finding |
| --- | --- |
| Deloitte RWE benchmark 2025 | 96% call RWD/RWE essential; 80% expect generative AI to affect RWE generation within a year [P]. Barriers: privacy and security 27%, talent 25%, regulatory uncertainty 23% [S] |
| TriNetX / studioID, Jul 2025, n=150 | Data compatibility is the top barrier (29%); 36% name data security when combining AI with RWD [P] |
| Norstella, Nov 2025, n=200 | Integration, quality and slow insight named as barriers, no figures [P] |
| Market size 2025 | USD 1.6B to 5.4B depending on scope; 9–16.5% yearly growth [S] |
| M&A | Datavant–Aetion (Jul 2025), Verana–COTA (Jan 2026), UBC–Evidinno (Jan 2026) [S] |

## 5. What a governance framework needs

Ranked by how consistently the three strands ask for it.

| # | Requirement | Regulation | Literature | Market |
| --- | --- | --- | --- | --- |
| 1 | Protocol and analysis plan locked and time-stamped before the outcome analysis; amendments versioned; other analyses labelled exploratory | FDA 2023; ICH M14; EMA 2025; HTA | HARPER; REPEAT; LEGEND | Protocol locking is table stakes |
| 2 | Executable specification as the record: code and cohort definition, with pinned data cut, CDM, vocabulary and ETL versions | FDA 2024 (traceability, transformations) | REPEAT; Ostropolets | Traceability from source to result |
| 3 | Fit-for-purpose assessment of the data for the question, before design | FDA 2024; ICH M14; EMA framework | SPIFD; DataSAT; DARWIN EU feasibility | Verantos, Flatiron |
| 4 | Operational definitions validated per data source, re-checked on reuse and on vocabulary change | FDA 2024 | PheValuator; vocabulary drift | Phenotype libraries |
| 5 | Design diagnostics against thresholds fixed in advance; all results reported | ICH M14 (bias, confounding) | LEGEND; negative controls | Rare |
| 6 | Data-use permission and purpose recorded per dataset and per study | FDA 2023 (data-owner agreements); EHDS permits; GDPR | Five Safes | Palantir |
| 7 | Data refresh as a governed event: re-run, diff, re-approve | FDA 2024 (QA/QC) | REPEAT (updated data) | Sentinel practice |
| 8 | Study registration and results release | HMA-EMA Catalogues; EHDS | RWE Transparency Initiative | Rare |
| 9 | Audit trail, access control, validated system, retention | Part 11; E6(R3) | Necessary hygiene | Table stakes |
| 10 | Record of AI use, human-validated | FDA draft; FDA-EMA principles | ELEVATE-GenAI; hallucinated codes | Unsettled |

What the evidence suggests is weak when used alone: a sign-off not tied to an artefact (a protocol
hash, a diagnostics result); counts of data-quality rules as a stand-in for fitness for purpose; and
cohort-count regression, since counts can stay stable while composition changes. This last judgement
is an inference from the studies above, not a finding any of them states.

## Sources

**US regulation**
- FDA, *Considerations for the Use of RWD and RWE* (2023): https://www.fda.gov/media/171667/download
- FDA, *Assessing EHR and Medical Claims Data* (2024): https://www.fda.gov/media/152503/download
- FDA, *Electronic Systems, Electronic Records, and Electronic Signatures: Q&A* (2024): https://www.fda.gov/media/166215/download
- FDA, ICH M14 final guidance: https://www.fda.gov/regulatory-information/search-fda-guidance-documents/m14-general-principles-planning-designing-analyzing-and-reporting-non-interventional-studies-utilize
- FDA, *RWE for Medical Devices* (2025): https://www.fda.gov/media/190201/download
- FDA press release, 15 Dec 2025: https://www.fda.gov/news-events/press-announcements/fda-eliminates-major-barrier-using-real-world-evidence-drug-and-device-application-reviews
- Federal Register, RFI on patient-level data, 12 Nov 2026: https://www.federalregister.gov/documents/2026/11/12/2026-22996/
- PDUFA VIII proposed commitment letter: https://www.fda.gov/media/193977/download
- FDA-EMA AI guiding principles: https://www.fda.gov/media/189581/download
- Sentinel, how data is obtained and checked: https://www.sentinelinitiative.org/about/how-sentinel-gets-its-data

**EU regulation**
- European Commission, EHDS: https://health.ec.europa.eu/ehealth-digital-health-and-care/european-health-data-space-regulation-ehds_en
- EMA, real-world evidence: https://www.ema.europa.eu/en/about-us/how-we-work/data-regulation-big-data-other-sources/real-world-evidence
- EMA, DARWIN EU: https://www.ema.europa.eu/en/about-us/how-we-work/big-data/real-world-evidence/data-analysis-real-world-interrogation-network-darwin-eu
- ENCePP, ICH M14 published: https://encepp.europa.eu/newsroom/news/ich-m14-guideline-published-2025-09-17_en
- ENCePP methodological guide: https://encepp.europa.eu/encepp-toolkit/methodological-guide_en
- EDPB guidelines: https://www.edpb.europa.eu/our-work-tools/general-guidance/guidelines-recommendations-best-practices_en
- European Commission, health technology assessment: https://health.ec.europa.eu/health-technology-assessment_en

**Literature**
- Wang SV et al., REPEAT, *Nat Commun* 2022: https://doi.org/10.1038/s41467-022-32310-3
- Ostropolets A et al., *JAMIA* 2023: https://doi.org/10.1093/jamia/ocad009
- Wang SV et al., RCT-DUPLICATE, *JAMA* 2023: https://doi.org/10.1001/jama.2023.4221
- Cashin AG et al., TARGET, *JAMA* 2025: https://doi.org/10.1001/jama.2025.13350
- Schuemie MJ et al., *Stat Med* 2014: https://doi.org/10.1002/sim.5925
- Voss EA et al., EHDEN, *JAMIA* 2023: https://doi.org/10.1093/jamia/ocad214
- Blacketer C et al., Data Quality Dashboard, *JAMIA* 2021: https://pmc.ncbi.nlm.nih.gov/articles/PMC8449628
- ELEVATE-GenAI, *Value Health* 2025: https://doi.org/10.1016/j.jval.2025.06.018

**Market**
- Datavant/Aetion compliance post: https://www.datavant.com/?p=6064
- Dataiku GxP workflows: https://dataiku.com/solutions/catalog/streamlined-gxp-workflows
- Domino GxP documentation: https://docs.dominodatalab.com/en/5.7/user_guide/1b8d2d/gxp
- Databricks GxP whitepaper: https://www.databricks.com/sites/default/files/2023-03/gxp-compliant-workloads-on-databricks.pdf
- Flatiron on regulatory-grade RWE: https://resources.flatiron.com/real-world-evidence/from-data-to-decisions-what-regulatory-grade-real-world-evidence-actually-requires
- Palantir Foundry governance: https://www.palantir.com/docs/foundry/security/data-protection-and-governance
- Deloitte RWE benchmark 2025: https://www.deloitte.com/us/en/what-we-do/capabilities/converge/articles/real-world-evidence-ai-in-pharmaceuticals.html
- TriNetX survey, Jul 2025: https://trinetx.com/press-releases/new-trinetx-survey-reveals-biopharmas-bold-embrace-of-real-world-data-and-artificial-intelligence-but-warns-of-looming-barriers/
- Norstella survey, Nov 2025: https://www.norstella.com/closing-strategy-gap/
