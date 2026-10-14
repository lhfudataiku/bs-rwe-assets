This zone creates OMOP clinical group concepts, including conditions, medications, and clinical visits for cohort characterization.

![flow-clinical-covariates.png](f5jnhZpiMROu)

 **Zone deliverables** : 
- [condition_group_occurrence](dataset:condition_group_occurrence): SNOMED concepts of clinical conditions and observations
- [charlson_score_occurrence](dataset:charlson_score_occurrence): charlson index representing disease burden. 
- [drug_class_exposure](dataset:drug_class_exposure): ATC drug class
- [visit_occurrence_labeled](dataset:visit_occurrence_labeled): OMOP clinical encounter concepts