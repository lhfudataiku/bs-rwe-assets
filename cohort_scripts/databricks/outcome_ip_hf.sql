CREATE TABLE @temp_database_schema.ucjke7uqCodesets  
USING DELTA
 AS
SELECT
CAST(NULL AS int) AS codeset_id,
	CAST(NULL AS bigint) AS concept_id  WHERE 1 = 0;
INSERT INTO @temp_database_schema.ucjke7uqCodesets (codeset_id, concept_id)
SELECT 0 as codeset_id, c.concept_id FROM (select distinct I.concept_id FROM
( 
 select concept_id from @vocabulary_database_schema.CONCEPT where concept_id in (262,9203,9201)
UNION select c.concept_id
 from @vocabulary_database_schema.CONCEPT c
 join @vocabulary_database_schema.CONCEPT_ANCESTOR ca on c.concept_id = ca.descendant_concept_id
 and ca.ancestor_concept_id in (262,9203,9201)
 and c.invalid_reason is null
) I
) C UNION ALL 
SELECT 1 as codeset_id, c.concept_id FROM (select distinct I.concept_id FROM
( 
 select concept_id from @vocabulary_database_schema.CONCEPT where concept_id in (316139)
UNION select c.concept_id
 from @vocabulary_database_schema.CONCEPT c
 join @vocabulary_database_schema.CONCEPT_ANCESTOR ca on c.concept_id = ca.descendant_concept_id
 and ca.ancestor_concept_id in (316139)
 and c.invalid_reason is null
) I
LEFT JOIN
(
 select concept_id from @vocabulary_database_schema.CONCEPT where concept_id in (315295)
UNION select c.concept_id
 from @vocabulary_database_schema.CONCEPT c
 join @vocabulary_database_schema.CONCEPT_ANCESTOR ca on c.concept_id = ca.descendant_concept_id
 and ca.ancestor_concept_id in (315295)
 and c.invalid_reason is null
) E ON I.concept_id = E.concept_id
WHERE E.concept_id is null
) C;
CREATE TABLE @temp_database_schema.ucjke7uqqualified_events
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
 select PE.person_id, PE.event_id, PE.start_date, PE.end_date, PE.visit_occurrence_id, PE.sort_date FROM (
-- Begin Visit Occurrence Criteria
select C.person_id, C.visit_occurrence_id as event_id, C.start_date, C.end_date,
 C.visit_occurrence_id, C.start_date as sort_date
from 
(
 select vo.person_id,vo.visit_occurrence_id,vo.visit_concept_id,vo.visit_start_date as start_date, vo.visit_end_date as end_date 
 FROM @cdm_database_schema.VISIT_OCCURRENCE vo
JOIN @temp_database_schema.ucjke7uqCodesets cs on (vo.visit_concept_id = cs.concept_id and cs.codeset_id = 0)
) C
-- End Visit Occurrence Criteria
) PE
JOIN (
-- Begin Criteria Group
select 0 as index_id, person_id, event_id
FROM
(
 select E.person_id, E.event_id 
 FROM (SELECT Q.person_id, Q.event_id, Q.start_date, Q.end_date, Q.visit_occurrence_id, OP.observation_period_start_date as op_start_date, OP.observation_period_end_date as op_end_date
FROM (-- Begin Visit Occurrence Criteria
select C.person_id, C.visit_occurrence_id as event_id, C.start_date, C.end_date,
 C.visit_occurrence_id, C.start_date as sort_date
from 
(
 select vo.person_id,vo.visit_occurrence_id,vo.visit_concept_id,vo.visit_start_date as start_date, vo.visit_end_date as end_date 
 FROM @cdm_database_schema.VISIT_OCCURRENCE vo
JOIN @temp_database_schema.ucjke7uqCodesets cs on (vo.visit_concept_id = cs.concept_id and cs.codeset_id = 0)
) C
-- End Visit Occurrence Criteria
) Q
JOIN @cdm_database_schema.OBSERVATION_PERIOD OP on Q.person_id = OP.person_id 
 and OP.observation_period_start_date <= Q.start_date and OP.observation_period_end_date >= Q.start_date
) E
 INNER JOIN
 (
 -- Begin Correlated Criteria
select 0 as index_id, cc.person_id, cc.event_id
from (SELECT p.person_id, p.event_id 
FROM (SELECT Q.person_id, Q.event_id, Q.start_date, Q.end_date, Q.visit_occurrence_id, OP.observation_period_start_date as op_start_date, OP.observation_period_end_date as op_end_date
FROM (-- Begin Visit Occurrence Criteria
select C.person_id, C.visit_occurrence_id as event_id, C.start_date, C.end_date,
 C.visit_occurrence_id, C.start_date as sort_date
from 
(
 select vo.person_id,vo.visit_occurrence_id,vo.visit_concept_id,vo.visit_start_date as start_date, vo.visit_end_date as end_date 
 FROM @cdm_database_schema.VISIT_OCCURRENCE vo
JOIN @temp_database_schema.ucjke7uqCodesets cs on (vo.visit_concept_id = cs.concept_id and cs.codeset_id = 0)
) C
-- End Visit Occurrence Criteria
) Q
JOIN @cdm_database_schema.OBSERVATION_PERIOD OP on Q.person_id = OP.person_id 
 and OP.observation_period_start_date <= Q.start_date and OP.observation_period_end_date >= Q.start_date
) P
JOIN (
 -- Begin Condition Occurrence Criteria
SELECT C.person_id, C.condition_occurrence_id as event_id, C.start_date, C.end_date,
 C.visit_occurrence_id, C.start_date as sort_date
FROM 
(
 SELECT co.person_id,co.condition_occurrence_id,co.condition_concept_id,co.visit_occurrence_id,co.condition_start_date as start_date, COALESCE(co.condition_end_date, date_add(co.condition_start_date, 1)) as end_date 
 FROM @cdm_database_schema.CONDITION_OCCURRENCE co
 JOIN @temp_database_schema.ucjke7uqCodesets cs on (co.condition_concept_id = cs.concept_id and cs.codeset_id = 1)
) C
-- End Condition Occurrence Criteria
) A on A.person_id = P.person_id AND A.START_DATE >= P.OP_START_DATE AND A.START_DATE <= P.OP_END_DATE AND A.START_DATE >= date_add(P.START_DATE, 0) AND A.START_DATE <= P.OP_END_DATE AND A.START_DATE >= P.OP_START_DATE AND A.START_DATE <= date_add(P.END_DATE, 0) ) cc 
GROUP BY cc.person_id, cc.event_id
HAVING COUNT(cc.event_id) >= 1
-- End Correlated Criteria
 ) CQ on E.person_id = CQ.person_id and E.event_id = CQ.event_id
 GROUP BY E.person_id, E.event_id
 HAVING COUNT(index_id) = 1
) G
-- End Criteria Group
) AC on AC.person_id = pe.person_id and AC.event_id = pe.event_id
 ) E
 JOIN @cdm_database_schema.observation_period OP on E.person_id = OP.person_id and E.start_date >= OP.observation_period_start_date and E.start_date <= op.observation_period_end_date
 WHERE date_add(OP.OBSERVATION_PERIOD_START_DATE, 0) <= E.START_DATE AND date_add(E.START_DATE, 0) <= OP.OBSERVATION_PERIOD_END_DATE
) P
-- End Primary Events
) pe
) QE
;
CREATE TABLE @temp_database_schema.ucjke7uqinclusion_events  
USING DELTA
 AS
SELECT
CAST(NULL AS bigint) AS inclusion_rule_id,
	CAST(NULL AS bigint) AS person_id,
	CAST(NULL AS bigint) AS event_id  WHERE 1 = 0;
CREATE TABLE @temp_database_schema.ucjke7uqincluded_events
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
 from @temp_database_schema.ucjke7uqqualified_events Q
 LEFT JOIN @temp_database_schema.ucjke7uqinclusion_events I on I.person_id = Q.person_id and I.event_id = Q.event_id
 GROUP BY Q.event_id, Q.person_id, Q.start_date, Q.end_date, Q.op_start_date, Q.op_end_date
 ) MG -- matching groups
) Results
;
CREATE TABLE @temp_database_schema.ucjke7uqstrategy_ends
USING DELTA
AS
SELECT
event_id, person_id, 
 case when date_add(end_date, 0) > op_end_date then op_end_date else date_add(end_date, 0) end as end_date
FROM
@temp_database_schema.ucjke7uqincluded_events;
CREATE TABLE @temp_database_schema.ucjke7uqcohort_rows
USING DELTA
AS
SELECT
person_id, start_date, end_date
FROM
( -- first_ends
 select F.person_id, F.start_date, F.end_date
 FROM (
 select I.event_id, I.person_id, I.start_date, CE.end_date, row_number() over (partition by I.person_id, I.event_id order by CE.end_date) as ordinal
 from @temp_database_schema.ucjke7uqincluded_events I
 join ( -- cohort_ends
-- cohort exit dates
-- End Date Strategy
SELECT event_id, person_id, end_date from @temp_database_schema.ucjke7uqstrategy_ends
 ) CE on I.event_id = CE.event_id and I.person_id = CE.person_id and CE.end_date >= I.start_date
 ) F
 WHERE F.ordinal = 1
) FE;
CREATE TABLE @temp_database_schema.ucjke7uqfinal_cohort
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
 FROM @temp_database_schema.ucjke7uqcohort_rows c
 JOIN ( -- cteEndDates
 SELECT
 person_id
 , date_add(event_date, -1 * 7) as end_date
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
 FROM @temp_database_schema.ucjke7uqcohort_rows
 UNION ALL
 SELECT
 person_id
 , date_add(end_date, 7) as end_date
 , 1 AS event_type
 FROM @temp_database_schema.ucjke7uqcohort_rows
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
FROM @temp_database_schema.ucjke7uqfinal_cohort CO
;
TRUNCATE TABLE @temp_database_schema.ucjke7uqstrategy_ends;
DROP TABLE @temp_database_schema.ucjke7uqstrategy_ends;
TRUNCATE TABLE @temp_database_schema.ucjke7uqcohort_rows;
DROP TABLE @temp_database_schema.ucjke7uqcohort_rows;
TRUNCATE TABLE @temp_database_schema.ucjke7uqfinal_cohort;
DROP TABLE @temp_database_schema.ucjke7uqfinal_cohort;
TRUNCATE TABLE @temp_database_schema.ucjke7uqinclusion_events;
DROP TABLE @temp_database_schema.ucjke7uqinclusion_events;
TRUNCATE TABLE @temp_database_schema.ucjke7uqqualified_events;
DROP TABLE @temp_database_schema.ucjke7uqqualified_events;
TRUNCATE TABLE @temp_database_schema.ucjke7uqincluded_events;
DROP TABLE @temp_database_schema.ucjke7uqincluded_events;
TRUNCATE TABLE @temp_database_schema.ucjke7uqCodesets;
DROP TABLE @temp_database_schema.ucjke7uqCodesets;
