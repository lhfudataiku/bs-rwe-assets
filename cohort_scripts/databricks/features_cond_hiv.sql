CREATE TABLE @temp_database_schema.jp70u0ihCodesets  
USING DELTA
 AS
SELECT
CAST(NULL AS int) AS codeset_id,
	CAST(NULL AS bigint) AS concept_id  WHERE 1 = 0;
INSERT INTO @temp_database_schema.jp70u0ihCodesets (codeset_id, concept_id)
SELECT 0 as codeset_id, c.concept_id FROM (select distinct I.concept_id FROM
( 
 select concept_id from @vocabulary_database_schema.CONCEPT where concept_id in (439727,374888,37017319,439727,37017320,439727,4013106,4092686,4241530)
UNION select c.concept_id
 from @vocabulary_database_schema.CONCEPT c
 join @vocabulary_database_schema.CONCEPT_ANCESTOR ca on c.concept_id = ca.descendant_concept_id
 and ca.ancestor_concept_id in (439727,4013106,4092686,4241530)
 and c.invalid_reason is null
) I
) C UNION ALL 
SELECT 1 as codeset_id, c.concept_id FROM (select distinct I.concept_id FROM
( 
 select concept_id from @vocabulary_database_schema.CONCEPT where concept_id in (1710612)
UNION select c.concept_id
 from @vocabulary_database_schema.CONCEPT c
 join @vocabulary_database_schema.CONCEPT_ANCESTOR ca on c.concept_id = ca.descendant_concept_id
 and ca.ancestor_concept_id in (1710612)
 and c.invalid_reason is null
) I
) C UNION ALL 
SELECT 4 as codeset_id, c.concept_id FROM (select distinct I.concept_id FROM
( 
 select concept_id from @vocabulary_database_schema.CONCEPT where concept_id in (4137604)
UNION select c.concept_id
 from @vocabulary_database_schema.CONCEPT c
 join @vocabulary_database_schema.CONCEPT_ANCESTOR ca on c.concept_id = ca.descendant_concept_id
 and ca.ancestor_concept_id in (4137604)
 and c.invalid_reason is null
) I
) C UNION ALL 
SELECT 5 as codeset_id, c.concept_id FROM (select distinct I.concept_id FROM
( 
 select concept_id from @vocabulary_database_schema.CONCEPT where concept_id in (439727,4092686)
) I
) C UNION ALL 
SELECT 6 as codeset_id, c.concept_id FROM (select distinct I.concept_id FROM
( 
 select concept_id from @vocabulary_database_schema.CONCEPT where concept_id in (1736971,1789428,1727223,964008,42874220,1756831,1747157,1724869,43560385,35200446,1738135,42874212,1703069,1717002,1758536,1736829,42544019,1711523,1704183,1738170,1787101,1715472,1769389,1712889,40238930,1748921,1746244,1781406,1710281,1736999,1724827,1710612,35605546,739588,1146410)
UNION select c.concept_id
 from @vocabulary_database_schema.CONCEPT c
 join @vocabulary_database_schema.CONCEPT_ANCESTOR ca on c.concept_id = ca.descendant_concept_id
 and ca.ancestor_concept_id in (1736971,1789428,1727223,964008,42874220,1756831,1747157,1724869,43560385,35200446,1738135,42874212,1703069,1717002,1758536,1736829,42544019,1711523,1704183,1738170,1787101,1715472,1769389,1712889,40238930,1748921,1746244,1781406,1710281,1736999,1724827,1710612,35605546,739588,1146410)
 and c.invalid_reason is null
) I
) C;
CREATE TABLE @temp_database_schema.jp70u0ihqualified_events
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
 -- Begin Condition Occurrence Criteria
SELECT C.person_id, C.condition_occurrence_id as event_id, C.start_date, C.end_date,
 C.visit_occurrence_id, C.start_date as sort_date
FROM 
(
 SELECT co.person_id,co.condition_occurrence_id,co.condition_concept_id,co.visit_occurrence_id,co.condition_start_date as start_date, COALESCE(co.condition_end_date, date_add(co.condition_start_date, 1)) as end_date , row_number() over (PARTITION BY co.person_id ORDER BY co.condition_start_date, co.condition_occurrence_id) as ordinal
 FROM @cdm_database_schema.CONDITION_OCCURRENCE co
 JOIN @temp_database_schema.jp70u0ihCodesets cs on (co.condition_concept_id = cs.concept_id and cs.codeset_id = 5)
) C
WHERE C.ordinal = 1
-- End Condition Occurrence Criteria
UNION ALL
-- Begin Measurement Criteria
select C.person_id, C.measurement_id as event_id, C.start_date, C.end_date,
 C.visit_occurrence_id, C.start_date as sort_date
from 
(
 select m.person_id,m.measurement_id,m.measurement_concept_id,m.visit_occurrence_id,m.value_as_number,m.range_high,m.range_low,m.measurement_date as start_date, date_add(m.measurement_date, 1) as end_date , row_number() over (PARTITION BY m.person_id ORDER BY m.measurement_date, m.measurement_id) as ordinal
 FROM @cdm_database_schema.MEASUREMENT m
JOIN @temp_database_schema.jp70u0ihCodesets cs on (m.measurement_concept_id = cs.concept_id and cs.codeset_id = 4)
) C
WHERE C.ordinal = 1
-- End Measurement Criteria
 ) E
 JOIN @cdm_database_schema.observation_period OP on E.person_id = OP.person_id and E.start_date >= OP.observation_period_start_date and E.start_date <= op.observation_period_end_date
 WHERE date_add(OP.OBSERVATION_PERIOD_START_DATE, 0) <= E.START_DATE AND date_add(E.START_DATE, 0) <= OP.OBSERVATION_PERIOD_END_DATE
) P
WHERE P.ordinal = 1
-- End Primary Events
) pe
) QE
;
CREATE TABLE @temp_database_schema.jp70u0ihInclusion_0
USING DELTA
AS
SELECT
0 as inclusion_rule_id, person_id, event_id
FROM
(
 select pe.person_id, pe.event_id
 FROM @temp_database_schema.jp70u0ihqualified_events pe
JOIN (
-- Begin Criteria Group
select 0 as index_id, person_id, event_id
FROM
(
 select E.person_id, E.event_id 
 FROM @temp_database_schema.jp70u0ihqualified_events E
 INNER JOIN
 (
 -- Begin Correlated Criteria
select 0 as index_id, cc.person_id, cc.event_id
from (SELECT p.person_id, p.event_id 
FROM @temp_database_schema.jp70u0ihqualified_events P
JOIN (
 -- Begin Condition Occurrence Criteria
SELECT C.person_id, C.condition_occurrence_id as event_id, C.start_date, C.end_date,
 C.visit_occurrence_id, C.start_date as sort_date
FROM 
(
 SELECT co.person_id,co.condition_occurrence_id,co.condition_concept_id,co.visit_occurrence_id,co.condition_start_date as start_date, COALESCE(co.condition_end_date, date_add(co.condition_start_date, 1)) as end_date 
 FROM @cdm_database_schema.CONDITION_OCCURRENCE co
 JOIN @temp_database_schema.jp70u0ihCodesets cs on (co.condition_concept_id = cs.concept_id and cs.codeset_id = 5)
) C
-- End Condition Occurrence Criteria
) A on A.person_id = P.person_id AND A.START_DATE >= P.OP_START_DATE AND A.START_DATE <= P.OP_END_DATE AND A.START_DATE >= date_add(P.START_DATE, 0) AND A.START_DATE <= date_add(P.START_DATE, 1) ) cc 
GROUP BY cc.person_id, cc.event_id
HAVING COUNT(cc.event_id) >= 1
-- End Correlated Criteria
UNION ALL
-- Begin Correlated Criteria
select 1 as index_id, cc.person_id, cc.event_id
from (SELECT p.person_id, p.event_id 
FROM @temp_database_schema.jp70u0ihqualified_events P
JOIN (
 -- Begin Drug Exposure Criteria
select C.person_id, C.drug_exposure_id as event_id, C.start_date, C.end_date,
 C.visit_occurrence_id,C.start_date as sort_date
from 
(
 select de.person_id,de.drug_exposure_id,de.drug_concept_id,de.visit_occurrence_id,days_supply,quantity,refills,de.drug_exposure_start_date as start_date, COALESCE(de.drug_exposure_end_date, date_add(de.drug_exposure_start_date, de.days_supply), date_add(de.drug_exposure_start_date, 1)) as end_date 
 FROM @cdm_database_schema.DRUG_EXPOSURE de
JOIN @temp_database_schema.jp70u0ihCodesets cs on (de.drug_concept_id = cs.concept_id and cs.codeset_id = 6)
) C
-- End Drug Exposure Criteria
) A on A.person_id = P.person_id AND A.START_DATE >= P.OP_START_DATE AND A.START_DATE <= P.OP_END_DATE AND A.START_DATE >= date_add(P.START_DATE, 0) AND A.START_DATE <= P.OP_END_DATE ) cc 
GROUP BY cc.person_id, cc.event_id
HAVING COUNT(cc.event_id) >= 2
-- End Correlated Criteria
 ) CQ on E.person_id = CQ.person_id and E.event_id = CQ.event_id
 GROUP BY E.person_id, E.event_id
 HAVING COUNT(index_id) > 0
) G
-- End Criteria Group
) AC on AC.person_id = pe.person_id AND AC.event_id = pe.event_id
) Results
;
CREATE TABLE @temp_database_schema.jp70u0ihinclusion_events
USING DELTA
AS
SELECT
inclusion_rule_id, person_id, event_id
FROM
(select inclusion_rule_id, person_id, event_id from @temp_database_schema.jp70u0ihInclusion_0) I;
TRUNCATE TABLE @temp_database_schema.jp70u0ihInclusion_0;
DROP TABLE @temp_database_schema.jp70u0ihInclusion_0;
CREATE TABLE @temp_database_schema.jp70u0ihincluded_events
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
 from @temp_database_schema.jp70u0ihqualified_events Q
 LEFT JOIN @temp_database_schema.jp70u0ihinclusion_events I on I.person_id = Q.person_id and I.event_id = Q.event_id
 GROUP BY Q.event_id, Q.person_id, Q.start_date, Q.end_date, Q.op_start_date, Q.op_end_date
 ) MG -- matching groups
 -- the matching group with all bits set ( POWER(2,# of inclusion rules) - 1 = inclusion_rule_mask
 WHERE (MG.inclusion_rule_mask = POWER(cast(2 as bigint),1)-1)
) Results
WHERE Results.ordinal = 1
;
CREATE TABLE @temp_database_schema.jp70u0ihcohort_rows
USING DELTA
AS
SELECT
person_id, start_date, end_date
FROM
( -- first_ends
 select F.person_id, F.start_date, F.end_date
 FROM (
 select I.event_id, I.person_id, I.start_date, CE.end_date, row_number() over (partition by I.person_id, I.event_id order by CE.end_date) as ordinal
 from @temp_database_schema.jp70u0ihincluded_events I
 join ( -- cohort_ends
-- cohort exit dates
-- By default, cohort exit at the event's op end date
select event_id, person_id, op_end_date as end_date from @temp_database_schema.jp70u0ihincluded_events
UNION ALL
-- Censor Events
select i.event_id, i.person_id, MIN(c.start_date) as end_date
FROM @temp_database_schema.jp70u0ihincluded_events i
JOIN
(
-- Begin Condition Occurrence Criteria
SELECT C.person_id, C.condition_occurrence_id as event_id, C.start_date, C.end_date,
 C.visit_occurrence_id, C.start_date as sort_date
FROM 
(
 SELECT co.person_id,co.condition_occurrence_id,co.condition_concept_id,co.visit_occurrence_id,co.condition_start_date as start_date, COALESCE(co.condition_end_date, date_add(co.condition_start_date, 1)) as end_date 
 FROM @cdm_database_schema.CONDITION_OCCURRENCE co
 JOIN @temp_database_schema.jp70u0ihCodesets cs on (co.condition_concept_id = cs.concept_id and cs.codeset_id = 1)
) C
-- End Condition Occurrence Criteria
) C on C.person_id = I.person_id and C.start_date >= I.start_date and C.START_DATE <= I.op_end_date
GROUP BY i.event_id, i.person_id
 ) CE on I.event_id = CE.event_id and I.person_id = CE.person_id and CE.end_date >= I.start_date
 ) F
 WHERE F.ordinal = 1
) FE;
CREATE TABLE @temp_database_schema.jp70u0ihfinal_cohort
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
 FROM @temp_database_schema.jp70u0ihcohort_rows c
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
 FROM @temp_database_schema.jp70u0ihcohort_rows
 UNION ALL
 SELECT
 person_id
 , date_add(end_date, 0) as end_date
 , 1 AS event_type
 FROM @temp_database_schema.jp70u0ihcohort_rows
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
FROM @temp_database_schema.jp70u0ihfinal_cohort CO
;
TRUNCATE TABLE @temp_database_schema.jp70u0ihcohort_rows;
DROP TABLE @temp_database_schema.jp70u0ihcohort_rows;
TRUNCATE TABLE @temp_database_schema.jp70u0ihfinal_cohort;
DROP TABLE @temp_database_schema.jp70u0ihfinal_cohort;
TRUNCATE TABLE @temp_database_schema.jp70u0ihinclusion_events;
DROP TABLE @temp_database_schema.jp70u0ihinclusion_events;
TRUNCATE TABLE @temp_database_schema.jp70u0ihqualified_events;
DROP TABLE @temp_database_schema.jp70u0ihqualified_events;
TRUNCATE TABLE @temp_database_schema.jp70u0ihincluded_events;
DROP TABLE @temp_database_schema.jp70u0ihincluded_events;
TRUNCATE TABLE @temp_database_schema.jp70u0ihCodesets;
DROP TABLE @temp_database_schema.jp70u0ihCodesets;
