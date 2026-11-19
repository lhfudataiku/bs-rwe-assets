CREATE TABLE @temp_database_schema.iz998u85Codesets  
USING DELTA
 AS
SELECT
CAST(NULL AS int) AS codeset_id,
	CAST(NULL AS bigint) AS concept_id  WHERE 1 = 0;
INSERT INTO @temp_database_schema.iz998u85Codesets (codeset_id, concept_id)
SELECT 0 as codeset_id, c.concept_id FROM (select distinct I.concept_id FROM
( 
 select concept_id from @vocabulary_database_schema.CONCEPT where concept_id in (316866)
UNION select c.concept_id
 from @vocabulary_database_schema.CONCEPT c
 join @vocabulary_database_schema.CONCEPT_ANCESTOR ca on c.concept_id = ca.descendant_concept_id
 and ca.ancestor_concept_id in (316866)
 and c.invalid_reason is null
) I
) C UNION ALL 
SELECT 1 as codeset_id, c.concept_id FROM (select distinct I.concept_id FROM
( 
 select concept_id from @vocabulary_database_schema.CONCEPT where concept_id in (1332418,40235485,1335471,1351557,1340128,1395058,1328165,1341927,1346686,1353776,1363749,974166,978555,1347384,1326012,1308216,1367500,907013,1310756,1318137,1318853,1319880,40226742,1373225,1331235,1334456,1317640,1342439,1308842,1307863)
UNION select c.concept_id
 from @vocabulary_database_schema.CONCEPT c
 join @vocabulary_database_schema.CONCEPT_ANCESTOR ca on c.concept_id = ca.descendant_concept_id
 and ca.ancestor_concept_id in (1332418,40235485,1335471,1351557,1340128,1395058,1328165,1341927,1346686,1353776,1363749,974166,978555,1347384,1326012,1308216,1367500,907013,1310756,1318137,1318853,1319880,40226742,1373225,1331235,1334456,1317640,1342439,1308842,1307863)
 and c.invalid_reason is null
) I
) C UNION ALL 
SELECT 2 as codeset_id, c.concept_id FROM (select distinct I.concept_id FROM
( 
 select concept_id from @vocabulary_database_schema.CONCEPT where concept_id in (1319998,1317967,991382,1332418,1314002,40235485,1335471,1322081,1338005,932745,1351557,1340128,1346823,1395058,1398937,1328165,1363053,1341927,1309799,1346686,1353776,1363749,956874,1344965,1373928,974166,978555,1347384,1326012,1386957,1308216,1367500,1305447,907013,1307046,1309068,1310756,1313200,1314577,1318137,1318853,1319880,40226742,1327978,1373225,1345858,1350489,1353766,1331235,1334456,970250,1317640,1341238,942350,1342439,904542,1308842,1307863)
UNION select c.concept_id
 from @vocabulary_database_schema.CONCEPT c
 join @vocabulary_database_schema.CONCEPT_ANCESTOR ca on c.concept_id = ca.descendant_concept_id
 and ca.ancestor_concept_id in (1319998,1317967,991382,1332418,1314002,40235485,1335471,1322081,1338005,932745,1351557,1340128,1346823,1395058,1398937,1328165,1363053,1341927,1309799,1346686,1353776,1363749,956874,1344965,1373928,974166,978555,1347384,1326012,1386957,1308216,1367500,1305447,907013,1307046,1309068,1310756,1313200,1314577,1318137,1318853,1319880,40226742,1327978,1373225,1345858,1350489,1353766,1331235,1334456,970250,1317640,1341238,942350,1342439,904542,1308842,1307863)
 and c.invalid_reason is null
) I
) C UNION ALL 
SELECT 3 as codeset_id, c.concept_id FROM (select distinct I.concept_id FROM
( 
 select concept_id from @vocabulary_database_schema.CONCEPT where concept_id in (1328165,1307863)
UNION select c.concept_id
 from @vocabulary_database_schema.CONCEPT c
 join @vocabulary_database_schema.CONCEPT_ANCESTOR ca on c.concept_id = ca.descendant_concept_id
 and ca.ancestor_concept_id in (1328165,1307863)
 and c.invalid_reason is null
) I
) C;
CREATE TABLE @temp_database_schema.iz998u85qualified_events
USING DELTA
AS
SELECT
event_id, person_id, start_date, end_date, op_start_date, op_end_date, visit_occurrence_id
FROM
(
 select pe.event_id, pe.person_id, pe.start_date, pe.end_date, pe.op_start_date, pe.op_end_date, row_number() over (partition by pe.person_id order by pe.start_date ASC) as ordinal, cast(pe.visit_occurrence_id as bigint) as visit_occurrence_id
 FROM (-- Begin Primary Events
select P.ordinal as event_id, P.person_id, P.start_date, P.end_date, op_start_date, op_end_date, cast(P.visit_occurrence_id as bigint) as visit_occurrence_id
FROM
(
 select E.person_id, E.start_date, E.end_date,
 row_number() OVER (PARTITION BY E.person_id ORDER BY E.sort_date ASC, E.event_id) ordinal,
 OP.observation_period_start_date as op_start_date, OP.observation_period_end_date as op_end_date, cast(E.visit_occurrence_id as bigint) as visit_occurrence_id
 FROM 
 (
 -- Begin Drug Exposure Criteria
select C.person_id, C.drug_exposure_id as event_id, C.start_date, C.end_date,
 C.visit_occurrence_id,C.start_date as sort_date
from 
(
 select de.person_id,de.drug_exposure_id,de.drug_concept_id,de.visit_occurrence_id,days_supply,quantity,refills,de.drug_exposure_start_date as start_date, COALESCE(de.drug_exposure_end_date, date_add(de.drug_exposure_start_date, de.days_supply), date_add(de.drug_exposure_start_date, 1)) as end_date , row_number() over (PARTITION BY de.person_id ORDER BY de.drug_exposure_start_date, de.drug_exposure_id) as ordinal
 FROM @cdm_database_schema.DRUG_EXPOSURE de
JOIN @temp_database_schema.iz998u85Codesets cs on (de.drug_concept_id = cs.concept_id and cs.codeset_id = 3)
) C
WHERE C.ordinal = 1
-- End Drug Exposure Criteria
 ) E
 JOIN @cdm_database_schema.observation_period OP on E.person_id = OP.person_id and E.start_date >= OP.observation_period_start_date and E.start_date <= op.observation_period_end_date
 WHERE date_add(OP.OBSERVATION_PERIOD_START_DATE, 365) <= E.START_DATE AND date_add(E.START_DATE, 0) <= OP.OBSERVATION_PERIOD_END_DATE
) P
WHERE P.ordinal = 1
-- End Primary Events
) pe
) QE
;
CREATE TABLE @temp_database_schema.iz998u85Inclusion_0
USING DELTA
AS
SELECT
0 as inclusion_rule_id, person_id, event_id
FROM
(
 select pe.person_id, pe.event_id
 FROM @temp_database_schema.iz998u85qualified_events pe
JOIN (
-- Begin Criteria Group
select 0 as index_id, person_id, event_id
FROM
(
 select E.person_id, E.event_id 
 FROM @temp_database_schema.iz998u85qualified_events E
 INNER JOIN
 (
 -- Begin Correlated Criteria
select 0 as index_id, cc.person_id, cc.event_id
from (SELECT p.person_id, p.event_id 
FROM @temp_database_schema.iz998u85qualified_events P
JOIN (
 -- Begin Condition Occurrence Criteria
SELECT C.person_id, C.condition_occurrence_id as event_id, C.start_date, C.end_date,
 C.visit_occurrence_id, C.start_date as sort_date
FROM 
(
 SELECT co.person_id,co.condition_occurrence_id,co.condition_concept_id,co.visit_occurrence_id,co.condition_start_date as start_date, COALESCE(co.condition_end_date, date_add(co.condition_start_date, 1)) as end_date 
 FROM @cdm_database_schema.CONDITION_OCCURRENCE co
 JOIN @temp_database_schema.iz998u85Codesets cs on (co.condition_concept_id = cs.concept_id and cs.codeset_id = 0)
) C
-- End Condition Occurrence Criteria
) A on A.person_id = P.person_id AND A.START_DATE >= P.OP_START_DATE AND A.START_DATE <= P.OP_END_DATE AND A.START_DATE >= date_add(P.START_DATE, -365) AND A.START_DATE <= date_add(P.START_DATE, 0) ) cc 
GROUP BY cc.person_id, cc.event_id
HAVING COUNT(cc.event_id) >= 1
-- End Correlated Criteria
 ) CQ on E.person_id = CQ.person_id and E.event_id = CQ.event_id
 GROUP BY E.person_id, E.event_id
 HAVING COUNT(index_id) = 1
) G
-- End Criteria Group
) AC on AC.person_id = pe.person_id AND AC.event_id = pe.event_id
) Results
;
CREATE TABLE @temp_database_schema.iz998u85Inclusion_1
USING DELTA
AS
SELECT
1 as inclusion_rule_id, person_id, event_id
FROM
(
 select pe.person_id, pe.event_id
 FROM @temp_database_schema.iz998u85qualified_events pe
JOIN (
-- Begin Criteria Group
select 0 as index_id, person_id, event_id
FROM
(
 select E.person_id, E.event_id 
 FROM @temp_database_schema.iz998u85qualified_events E
 INNER JOIN
 (
 -- Begin Correlated Criteria
select 0 as index_id, p.person_id, p.event_id
from @temp_database_schema.iz998u85qualified_events p
LEFT JOIN (
SELECT p.person_id, p.event_id 
FROM @temp_database_schema.iz998u85qualified_events P
JOIN (
 -- Begin Drug Exposure Criteria
select C.person_id, C.drug_exposure_id as event_id, C.start_date, C.end_date,
 C.visit_occurrence_id,C.start_date as sort_date
from 
(
 select de.person_id,de.drug_exposure_id,de.drug_concept_id,de.visit_occurrence_id,days_supply,quantity,refills,de.drug_exposure_start_date as start_date, COALESCE(de.drug_exposure_end_date, date_add(de.drug_exposure_start_date, de.days_supply), date_add(de.drug_exposure_start_date, 1)) as end_date 
 FROM @cdm_database_schema.DRUG_EXPOSURE de
JOIN @temp_database_schema.iz998u85Codesets cs on (de.drug_concept_id = cs.concept_id and cs.codeset_id = 2)
) C
-- End Drug Exposure Criteria
) A on A.person_id = P.person_id AND A.START_DATE >= P.OP_START_DATE AND A.START_DATE <= P.OP_END_DATE AND A.START_DATE >= P.OP_START_DATE AND A.START_DATE <= date_add(P.START_DATE, -1) ) cc on p.person_id = cc.person_id and p.event_id = cc.event_id
GROUP BY p.person_id, p.event_id
HAVING COUNT(cc.event_id) = 0
-- End Correlated Criteria
 ) CQ on E.person_id = CQ.person_id and E.event_id = CQ.event_id
 GROUP BY E.person_id, E.event_id
 HAVING COUNT(index_id) = 1
) G
-- End Criteria Group
) AC on AC.person_id = pe.person_id AND AC.event_id = pe.event_id
) Results
;
CREATE TABLE @temp_database_schema.iz998u85Inclusion_2
USING DELTA
AS
SELECT
2 as inclusion_rule_id, person_id, event_id
FROM
(
 select pe.person_id, pe.event_id
 FROM @temp_database_schema.iz998u85qualified_events pe
JOIN (
-- Begin Criteria Group
select 0 as index_id, person_id, event_id
FROM
(
 select E.person_id, E.event_id 
 FROM @temp_database_schema.iz998u85qualified_events E
 INNER JOIN
 (
 -- Begin Correlated Criteria
select 0 as index_id, cc.person_id, cc.event_id
from (SELECT p.person_id, p.event_id , A.domain_concept_id
FROM @temp_database_schema.iz998u85qualified_events P
JOIN (
 -- Begin Drug Era Criteria
select C.person_id, C.drug_era_id as event_id, C.start_date, C.end_date,
 CAST(NULL as bigint) as visit_occurrence_id,C.start_date as sort_date, C.drug_concept_id as domain_concept_id
from 
(
 select de.person_id,de.drug_era_id,de.drug_concept_id,de.drug_exposure_count,de.gap_days,de.drug_era_start_date as start_date, de.drug_era_end_date as end_date 
 FROM @cdm_database_schema.DRUG_ERA de
where de.drug_concept_id in (SELECT concept_id from @temp_database_schema.iz998u85Codesets where codeset_id = 2)
) C
-- End Drug Era Criteria
) A on A.person_id = P.person_id AND A.START_DATE >= P.OP_START_DATE AND A.START_DATE <= P.OP_END_DATE AND A.START_DATE >= date_add(P.START_DATE, 0) AND A.START_DATE <= date_add(P.START_DATE, 7) ) cc 
GROUP BY cc.person_id, cc.event_id
HAVING COUNT(DISTINCT cc.domain_concept_id) = 1
-- End Correlated Criteria
 ) CQ on E.person_id = CQ.person_id and E.event_id = CQ.event_id
 GROUP BY E.person_id, E.event_id
 HAVING COUNT(index_id) = 1
) G
-- End Criteria Group
) AC on AC.person_id = pe.person_id AND AC.event_id = pe.event_id
) Results
;
CREATE TABLE @temp_database_schema.iz998u85inclusion_events
USING DELTA
AS
SELECT
inclusion_rule_id, person_id, event_id
FROM
(select inclusion_rule_id, person_id, event_id from @temp_database_schema.iz998u85Inclusion_0
UNION ALL
select inclusion_rule_id, person_id, event_id from @temp_database_schema.iz998u85Inclusion_1
UNION ALL
select inclusion_rule_id, person_id, event_id from @temp_database_schema.iz998u85Inclusion_2) I;
TRUNCATE TABLE @temp_database_schema.iz998u85Inclusion_0;
DROP TABLE @temp_database_schema.iz998u85Inclusion_0;
TRUNCATE TABLE @temp_database_schema.iz998u85Inclusion_1;
DROP TABLE @temp_database_schema.iz998u85Inclusion_1;
TRUNCATE TABLE @temp_database_schema.iz998u85Inclusion_2;
DROP TABLE @temp_database_schema.iz998u85Inclusion_2;
CREATE TABLE @temp_database_schema.iz998u85included_events
USING DELTA
AS
SELECT
event_id, person_id, start_date, end_date, op_start_date, op_end_date
FROM
(
 SELECT event_id, person_id, start_date, end_date, op_start_date, op_end_date, row_number() over (partition by person_id order by start_date ASC) as ordinal
 from
 (
 select Q.event_id, Q.person_id, Q.start_date, Q.end_date, Q.op_start_date, Q.op_end_date, SUM(coalesce(POWER(cast(2 as bigint), I.inclusion_rule_id), 0)) as inclusion_rule_mask
 from @temp_database_schema.iz998u85qualified_events Q
 LEFT JOIN @temp_database_schema.iz998u85inclusion_events I on I.person_id = Q.person_id and I.event_id = Q.event_id
 GROUP BY Q.event_id, Q.person_id, Q.start_date, Q.end_date, Q.op_start_date, Q.op_end_date
 ) MG -- matching groups
 -- the matching group with all bits set ( POWER(2,# of inclusion rules) - 1 = inclusion_rule_mask
 WHERE (MG.inclusion_rule_mask = POWER(cast(2 as bigint),3)-1)
) Results
WHERE Results.ordinal = 1
;
DROP VIEW IF EXISTS ctePersons ; CREATE TEMPORARY VIEW ctePersons  AS (select distinct person_id from @temp_database_schema.iz998u85included_events
);
 CREATE TABLE @temp_database_schema.iz998u85drugTarget
USING DELTA
AS
(SELECT
person_id, drug_exposure_start_date, drug_exposure_end_date
FROM
(
 select de.PERSON_ID, DRUG_EXPOSURE_START_DATE, COALESCE(DRUG_EXPOSURE_END_DATE, date_add(DRUG_EXPOSURE_START_DATE, DAYS_SUPPLY), date_add(DRUG_EXPOSURE_START_DATE, 1)) as DRUG_EXPOSURE_END_DATE 
 FROM @cdm_database_schema.DRUG_EXPOSURE de
 JOIN ctePersons p on de.person_id = p.person_id
 JOIN @temp_database_schema.iz998u85Codesets cs on cs.codeset_id = 3 AND de.drug_concept_id = cs.concept_id
 UNION ALL
 select de.PERSON_ID, DRUG_EXPOSURE_START_DATE, COALESCE(DRUG_EXPOSURE_END_DATE, date_add(DRUG_EXPOSURE_START_DATE, DAYS_SUPPLY), date_add(DRUG_EXPOSURE_START_DATE, 1)) as DRUG_EXPOSURE_END_DATE 
 FROM @cdm_database_schema.DRUG_EXPOSURE de
 JOIN ctePersons p on de.person_id = p.person_id
 JOIN @temp_database_schema.iz998u85Codesets cs on cs.codeset_id = 3 AND de.drug_source_concept_id = cs.concept_id
) E
);
CREATE TABLE @temp_database_schema.iz998u85strategy_ends
USING DELTA
AS
SELECT
et.event_id, et.person_id, ERAS.era_end_date as end_date
FROM
@temp_database_schema.iz998u85included_events et
JOIN 
(
 select ENDS.person_id, min(drug_exposure_start_date) as era_start_date, date_add(ENDS.era_end_date, 0) as era_end_date
 from
 (
 select de.person_id, de.drug_exposure_start_date, MIN(e.END_DATE) as era_end_date
 FROM @temp_database_schema.iz998u85drugTarget DE
 JOIN 
 (
 --cteEndDates
 select PERSON_ID, date_add(EVENT_DATE, -1 * 30) as END_DATE -- unpad the end date by 30
 FROM
 (
 select PERSON_ID, EVENT_DATE, EVENT_TYPE, 
 MAX(START_ORDINAL) OVER (PARTITION BY PERSON_ID ORDER BY event_date, event_type, START_ORDINAL ROWS UNBOUNDED PRECEDING) AS start_ordinal,
 ROW_NUMBER() OVER (PARTITION BY PERSON_ID ORDER BY EVENT_DATE, EVENT_TYPE, START_ORDINAL) AS OVERALL_ORD -- this re-numbers the inner UNION so all rows are numbered ordered by the event date
 from
 (
 -- select the start dates, assigning a row number to each
 Select PERSON_ID, DRUG_EXPOSURE_START_DATE AS EVENT_DATE, 0 as EVENT_TYPE, ROW_NUMBER() OVER (PARTITION BY PERSON_ID ORDER BY DRUG_EXPOSURE_START_DATE) as START_ORDINAL
 from @temp_database_schema.iz998u85drugTarget D
 UNION ALL
 -- add the end dates with NULL as the row number, padding the end dates by 30 to allow a grace period for overlapping ranges.
 select PERSON_ID, date_add(DRUG_EXPOSURE_END_DATE, 30), 1 as EVENT_TYPE, NULL
 FROM @temp_database_schema.iz998u85drugTarget D
 ) RAWDATA
 ) E
 WHERE 2 * E.START_ORDINAL - E.OVERALL_ORD = 0
 ) E on DE.PERSON_ID = E.PERSON_ID and E.END_DATE >= DE.DRUG_EXPOSURE_START_DATE
 GROUP BY de.person_id, de.drug_exposure_start_date
 ) ENDS
 GROUP BY ENDS.person_id, ENDS.era_end_date
) ERAS on ERAS.person_id = et.person_id 
WHERE et.start_date between ERAS.era_start_date and ERAS.era_end_date;
TRUNCATE TABLE @temp_database_schema.iz998u85drugTarget;
DROP TABLE @temp_database_schema.iz998u85drugTarget;
CREATE TABLE @temp_database_schema.iz998u85cohort_rows
USING DELTA
AS
SELECT
person_id, start_date, end_date
FROM
( -- first_ends
 select F.person_id, F.start_date, F.end_date
 FROM (
 select I.event_id, I.person_id, I.start_date, CE.end_date, row_number() over (partition by I.person_id, I.event_id order by CE.end_date) as ordinal
 from @temp_database_schema.iz998u85included_events I
 join ( -- cohort_ends
-- cohort exit dates
-- By default, cohort exit at the event's op end date
select event_id, person_id, op_end_date as end_date from @temp_database_schema.iz998u85included_events
UNION ALL
-- End Date Strategy
SELECT event_id, person_id, end_date from @temp_database_schema.iz998u85strategy_ends
 ) CE on I.event_id = CE.event_id and I.person_id = CE.person_id and CE.end_date >= I.start_date
 ) F
 WHERE F.ordinal = 1
) FE;
CREATE TABLE @temp_database_schema.iz998u85final_cohort
USING DELTA
AS
SELECT
person_id, min(start_date) as start_date, end_date
FROM
( --cteEnds
 SELECT
 c.person_id
 , c.start_date
 , MIN(ed.end_date) AS end_date
 FROM @temp_database_schema.iz998u85cohort_rows c
 JOIN ( -- cteEndDates
 SELECT
 person_id
 , date_add(event_date, -1 * 0) as end_date
 FROM
 (
 SELECT
 person_id
 , event_date
 , event_type
 , SUM(event_type) OVER (PARTITION BY person_id ORDER BY event_date, event_type ROWS UNBOUNDED PRECEDING) AS interval_status
 FROM
 (
 SELECT
 person_id
 , start_date AS event_date
 , -1 AS event_type
 FROM @temp_database_schema.iz998u85cohort_rows
 UNION ALL
 SELECT
 person_id
 , date_add(end_date, 0) as end_date
 , 1 AS event_type
 FROM @temp_database_schema.iz998u85cohort_rows
 ) RAWDATA
 ) e
 WHERE interval_status = 0
 ) ed ON c.person_id = ed.person_id AND ed.end_date >= c.start_date
 GROUP BY c.person_id, c.start_date
) e
group by person_id, end_date
;
DELETE FROM @target_database_schema.@target_cohort_table where cohort_definition_id = @target_cohort_id;
INSERT INTO @target_database_schema.@target_cohort_table (cohort_definition_id, subject_id, cohort_start_date, cohort_end_date)
select @target_cohort_id as cohort_definition_id, person_id, start_date, end_date 
FROM @temp_database_schema.iz998u85final_cohort CO
;
TRUNCATE TABLE @temp_database_schema.iz998u85strategy_ends;
DROP TABLE @temp_database_schema.iz998u85strategy_ends;
TRUNCATE TABLE @temp_database_schema.iz998u85cohort_rows;
DROP TABLE @temp_database_schema.iz998u85cohort_rows;
TRUNCATE TABLE @temp_database_schema.iz998u85final_cohort;
DROP TABLE @temp_database_schema.iz998u85final_cohort;
TRUNCATE TABLE @temp_database_schema.iz998u85inclusion_events;
DROP TABLE @temp_database_schema.iz998u85inclusion_events;
TRUNCATE TABLE @temp_database_schema.iz998u85qualified_events;
DROP TABLE @temp_database_schema.iz998u85qualified_events;
TRUNCATE TABLE @temp_database_schema.iz998u85included_events;
DROP TABLE @temp_database_schema.iz998u85included_events;
TRUNCATE TABLE @temp_database_schema.iz998u85Codesets;
DROP TABLE @temp_database_schema.iz998u85Codesets;
